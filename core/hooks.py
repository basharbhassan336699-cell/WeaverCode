"""
hooks.py — نظام hooks دورة الحياة لـ WeaverCode
================================================

يشغّل أوامر shell خارجية عند أحداث محددة، مماثل لـ hooks في Claude Code:

الأحداث المدعومة:
    - UserPromptSubmit : قبل إرسال رسالة المستخدم
    - PreToolUse       : قبل تنفيذ أداة  (يمكنه منع التنفيذ)
    - PostToolUse      : بعد تنفيذ أداة
    - Stop             : عند انتهاء الرد

الإعداد من `.claude/hooks.json` (أو `config/hooks.json`):
{
  "PreToolUse": [
    { "matcher": "Bash|Write", "command": "echo \"$WEAVER_TOOL\" >> ~/.weaver/audit.log" }
  ],
  "PostToolUse": [
    { "command": "echo done" }
  ]
}

يُمرَّر للـ hook متغيرات بيئة: WEAVER_EVENT, WEAVER_TOOL, WEAVER_TOOL_ARGS (JSON), WEAVER_PROMPT.
إذا أرجع hook في PreToolUse رمز خروج غير صفري، يُمنع تنفيذ الأداة (deny).
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any


class HookManager:
    """محمّل ومشغّل hooks دورة الحياة"""

    EVENTS = (
        "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop",
        "SessionStart", "SessionEnd", "PreCompact", "PostCompact",
        "InstructionsLoaded",
    )

    def __init__(self, config_path: Optional[Path] = None,
                 load_plugins: bool = True):
        self._hooks: Dict[str, List[Dict[str, str]]] = {}
        # رسائل asyncRewake المُعلّقة (إن أرجعها hook ليعيد تنبيه الوكيل)
        self._pending_rewake: List[str] = []
        # دمج hooks الإضافات (plugins) تلقائياً؛ يمكن تعطيله عبر
        # WEAVER_LOAD_PLUGINS=0 أو تمرير load_plugins=False (للاختبارات/الأداء).
        self._load_plugins = load_plugins and os.environ.get(
            "WEAVER_LOAD_PLUGINS", "1").strip().lower() not in ("0", "false", "off", "no")
        self.config_path = self._resolve_config(config_path)
        self.load()

    def _resolve_config(self, config_path: Optional[Path]) -> Optional[Path]:
        if config_path:
            return Path(config_path)
        root = Path(__file__).resolve().parent.parent
        for candidate in (root / ".claude" / "hooks.json",
                          root / "config" / "hooks.json"):
            if candidate.exists():
                return candidate
        return None

    def load(self) -> None:
        self._hooks.clear()
        # (1) hooks المستخدم من hooks.json (إن وُجد)
        if self.config_path and self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
            for event in self.EVENTS:
                entries = data.get(event, [])
                if isinstance(entries, list):
                    self._hooks[event] = [e for e in entries
                                          if isinstance(e, dict) and e.get("command")]
        # (2) دمج hooks الإضافات (plugins) — يعمل حتى بلا hooks.json للمستخدم
        self.merge_plugin_hooks()

    def has_any(self) -> bool:
        return any(self._hooks.values())

    @staticmethod
    def _matches(matcher: Optional[str], tool_name: str) -> bool:
        if not matcher:
            return True
        import re
        try:
            return re.search(matcher, tool_name or "") is not None
        except re.error:
            return matcher == tool_name

    def run(
        self,
        event: str,
        tool_name: str = "",
        tool_args: Optional[Dict[str, Any]] = None,
        prompt: str = "",
    ) -> bool:
        """
        تشغيل كل hooks المطابقة للحدث.
        يُرجع False إذا منع أحد hooks (PreToolUse) التنفيذ (رمز خروج ≠ 0)، وإلا True.
        """
        entries = self._hooks.get(event, [])
        if not entries:
            return True

        env = dict(os.environ)
        env["WEAVER_EVENT"] = event
        env["WEAVER_TOOL"] = tool_name or ""
        env["WEAVER_TOOL_ARGS"] = json.dumps(tool_args or {}, ensure_ascii=False)
        env["WEAVER_PROMPT"] = prompt or ""

        allowed = True
        for entry in entries:
            if not self._matches(entry.get("matcher"), tool_name):
                continue
            # شرط if (صيغة: Bool مثل "Bash(git commit:*)") — إضافي، يتخطّى إن لم يطابق
            if entry.get("if") and not self._check_if_condition(
                    entry["if"], tool_name, tool_args):
                continue
            command = entry.get("command")
            if not command:
                continue
            timeout = int(entry.get("timeout", 30))
            try:
                proc = subprocess.run(
                    command, shell=True, capture_output=True, text=True,
                    timeout=timeout, env=env,
                )
                # في PreToolUse فقط: رمز خروج غير صفري يمنع الأداة
                if event == "PreToolUse" and proc.returncode != 0:
                    allowed = False
                # asyncRewake: يجمع مخرجات الـ hook لإعادة تنبيه الوكيل لاحقاً
                if entry.get("asyncRewake") and (proc.stdout or "").strip() \
                        and proc.returncode != 0:
                    msg = entry.get("rewakeMessage", "")
                    out = proc.stdout.strip()
                    self._pending_rewake.append(f"{msg}\n\n{out}" if msg else out)
            except Exception:
                # فشل hook لا يُسقط النظام؛ يُتجاهَل بأمان
                continue
        return allowed

    def _check_if_condition(self, condition: str, tool_name: str,
                            tool_args: Any) -> bool:
        """فحص شرط if بصيغة ToolName(pattern:*) — مثل Bash(git commit:*)."""
        import re as _re
        m = _re.match(r"^(\w+)\((.+)\)$", (condition or "").strip())
        if not m:
            return True  # شرط غير معروف = لا يمنع
        cond_tool, cond_pattern = m.group(1), m.group(2)
        if cond_tool != tool_name:
            return False
        if isinstance(tool_args, dict):
            cmd = tool_args.get("command", "") or tool_args.get("cmd", "")
        else:
            cmd = str(tool_args or "")
        pattern = _re.escape(cond_pattern).replace(r"\*", ".*")
        return bool(_re.search(pattern, cmd))

    def pop_rewake(self) -> str:
        """سحب رسائل asyncRewake المُعلّقة (وتفريغها). يُرجع '' إن لا شيء."""
        if not self._pending_rewake:
            return ""
        msg = "\n\n---\n\n".join(self._pending_rewake)
        self._pending_rewake = []
        return msg

    # ── أحداث الجلسة والتلخيص (SessionStart / PreCompact / ...) ───────────────

    def run_session_start(self) -> str:
        """
        تشغيل SessionStart hooks وجمع additionalContext منها.
        يُرجع نصاً يُضاف إلى system prompt في بداية الجلسة.
        """
        entries = self._hooks.get("SessionStart", [])
        context_parts: List[str] = []
        env = dict(os.environ)
        env["WEAVER_EVENT"] = "SessionStart"
        for entry in entries:
            command = entry.get("command", "")
            timeout = int(entry.get("timeout", 30))
            if not command:
                continue
            try:
                proc = subprocess.run(
                    command, shell=True, capture_output=True,
                    text=True, timeout=timeout, env=env,
                )
                if proc.stdout.strip():
                    # محاولة استخراج additionalContext من JSON
                    try:
                        data = json.loads(proc.stdout)
                        ctx = (data.get("hookSpecificOutput", {})
                                   .get("additionalContext", ""))
                        if ctx:
                            context_parts.append(ctx)
                    except (json.JSONDecodeError, AttributeError):
                        # مخرج نصي عادي
                        context_parts.append(proc.stdout.strip())
            except Exception:
                continue
        return "\n\n".join(context_parts)

    def run_pre_compact(self, summary_so_far: str = "") -> tuple:
        """
        تشغيل PreCompact hooks.
        يُرجع (True, extra_context) إذا سُمح بالتلخيص،
        و(False, "") إذا مُنع بـ exit 2.
        """
        entries = self._hooks.get("PreCompact", [])
        if not entries:
            return True, ""
        env = dict(os.environ)
        env["WEAVER_EVENT"] = "PreCompact"
        env["WEAVER_COMPACT_SUMMARY"] = summary_so_far
        context_parts: List[str] = []
        for entry in entries:
            command = entry.get("command", "")
            timeout = int(entry.get("timeout", 30))
            if not command:
                continue
            try:
                proc = subprocess.run(
                    command, shell=True, capture_output=True,
                    text=True, timeout=timeout, env=env,
                )
                if proc.returncode == 2:
                    return False, ""
                if proc.stdout.strip():
                    context_parts.append(proc.stdout.strip())
            except Exception:
                continue
        return True, "\n".join(context_parts)

    def run_session_end(self) -> None:
        self.run("SessionEnd")

    def run_post_compact(self, summary: str = "") -> None:
        self._run_with_env("PostCompact", {"WEAVER_COMPACT_SUMMARY": summary})

    def run_instructions_loaded(self, claude_md_path: str = "") -> None:
        self._run_with_env("InstructionsLoaded",
                           {"WEAVER_INSTRUCTIONS_PATH": claude_md_path})

    def _run_with_env(self, event: str, extra_env: dict) -> None:
        entries = self._hooks.get(event, [])
        if not entries:
            return
        env = dict(os.environ)
        env["WEAVER_EVENT"] = event
        env.update(extra_env)
        for entry in entries:
            command = entry.get("command", "")
            timeout = int(entry.get("timeout", 30))
            if not command:
                continue
            try:
                subprocess.run(
                    command, shell=True, capture_output=True,
                    text=True, timeout=timeout, env=env,
                )
            except Exception:
                continue

    # ── دمج hooks الإضافات (plugins) مع hooks المستخدم ────────────────────────

    def merge_plugin_hooks(self) -> None:
        """دمج hooks الموجودة في plugins مع hooks المستخدم (إضافةً لا استبدالاً)."""
        if not self._load_plugins:
            return
        try:
            from core.plugins import PluginLoader
            pl = PluginLoader()
            plugin_hooks = pl.get_all_hooks()
            for event, entries in plugin_hooks.items():
                if event in self.EVENTS and entries:
                    self._hooks.setdefault(event, []).extend(entries)
        except Exception:
            pass
