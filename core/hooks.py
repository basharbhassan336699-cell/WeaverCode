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

    EVENTS = ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop")

    def __init__(self, config_path: Optional[Path] = None):
        self._hooks: Dict[str, List[Dict[str, str]]] = {}
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
        if not self.config_path or not self.config_path.exists():
            return
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return
        for event in self.EVENTS:
            entries = data.get(event, [])
            if isinstance(entries, list):
                self._hooks[event] = [e for e in entries if isinstance(e, dict) and e.get("command")]

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
            command = entry["command"]
            timeout = int(entry.get("timeout", 30))
            try:
                proc = subprocess.run(
                    command, shell=True, capture_output=True, text=True,
                    timeout=timeout, env=env,
                )
                # في PreToolUse فقط: رمز خروج غير صفري يمنع الأداة
                if event == "PreToolUse" and proc.returncode != 0:
                    allowed = False
            except Exception:
                # فشل hook لا يُسقط النظام؛ يُتجاهَل بأمان
                continue
        return allowed
