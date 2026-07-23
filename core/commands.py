"""
commands.py — نظام أوامر السلاش (/command) لـ WeaverCode
=========================================================

يحمّل ملفات الأوامر من `.claude/commands/*.md` ويشغّلها كقوالب بروموه.
كل ملف أمر = قالب نصّي (Markdown) قد يبدأ بـ frontmatter (بين ---).

الاستخدام في الوضع التفاعلي:
    /weaver-status            → يشغّل .claude/commands/weaver-status.md كبروموه
    /review core/ui.py        → يستبدل $ARGUMENTS بـ "core/ui.py" ثم يشغّله

بهذا تعمل الأوامر الـ16 الموجودة فعلياً داخل محرّك WeaverCode لا كملفات معطّلة.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── محلّل الأوامر التفاعلية المدمجة ──────────────────────────────────────────
# يتعرّف على أوامر التحكّم (/plan, /approve, …) ويُرجع فعلاً منظّماً + رسالة
# تأكيد عربية. قابل للتوسيع: أضف مدخلاً في _PARSE_TABLE فقط.

_PARSE_TABLE = [
    # (أنماط النص, الفعل, رسالة التأكيد)
    (("/plan", "/plan on"), "plan_on",
     "✅ وضع التخطيط مُفعّل — سيولّد النموذج خطة دون تنفيذ أي تعديل."),
    (("/plan off",), "plan_off",
     "⏹️ وضع التخطيط معطّل — عاد التنفيذ الطبيعي."),
    (("/approve", "/execute"), "approve",
     "🚀 جارٍ تنفيذ الخطة المعتمدة…"),
    (("/plan status",), "plan_status",
     "📋 حالة وضع التخطيط."),
]


def parse(text: str) -> Optional[Dict[str, str]]:
    """يحلّل أمر سلاش تفاعلياً معروفاً.

    يُرجع {"action": ..., "message": ..., "args": ...} أو None إن لم يكن أمراً
    معروفاً (فيُعامل النص كبروموه عادي أو أمر ملفّي من SlashCommands).
    """
    t = (text or "").strip()
    if not t.startswith("/"):
        return None
    low = t.lower()
    best = None  # الأطول نمطاً يفوز (فلا يبتلع /plan النمطَ /plan off)
    for patterns, action, message in _PARSE_TABLE:
        for p in patterns:
            if (low == p or low.startswith(p + " ")) and \
                    (best is None or len(p) > best[0]):
                best = (len(p), action, message, t[len(p):].strip())
    if best:
        return {"action": best[1], "message": best[2], "args": best[3]}
    return None


class SlashCommands:
    """محمّل ومشغّل أوامر السلاش من مجلد .claude/commands"""

    def __init__(self, commands_dir: Optional[Path] = None):
        if commands_dir is None:
            commands_dir = Path(__file__).resolve().parent.parent / ".claude" / "commands"
        self.commands_dir = Path(commands_dir)
        self._commands: Dict[str, Path] = {}
        self.reload()

    def reload(self) -> None:
        """إعادة مسح مجلد الأوامر + أوامر الإضافات (plugins)."""
        self._commands.clear()
        # (1) أوامر .claude/commands لها الأولوية
        if self.commands_dir.exists():
            for md in sorted(self.commands_dir.glob("*.md")):
                self._commands[md.stem] = md
        # (2) أوامر الإضافات: تُتاح بالاسم الكامل «plugin/command» ودائماً،
        #     وبالاسم المختصر «command» إن لم يكن محجوزاً (الأولوية لما سبق).
        try:
            from core.plugins import PluginLoader
            for full_name, path in PluginLoader().get_all_commands().items():
                self._commands[full_name] = path
                stem = full_name.split("/", 1)[-1]
                self._commands.setdefault(stem, path)
        except Exception:
            pass  # الإضافات اختيارية — لا تُسقط أوامر السلاش الأساسية

    def names(self) -> List[str]:
        return sorted(self._commands.keys())

    def _description_of(self, path: Path) -> str:
        """قراءة وصف الأمر من frontmatter (يدعم الوصف متعدّد الأسطر '|')."""
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            return ""
        _body, meta = self._strip_frontmatter(raw)
        desc = meta.get("description", "").strip()
        if desc in ("|", ">", "|-", ">-", ""):
            # وصف متعدّد الأسطر: خذ أول سطر غير فارغ بعد ---
            m = re.match(r"^---\s*\n(.*?)\n---", raw, re.DOTALL)
            if m:
                after = False
                for line in m.group(1).splitlines():
                    s = line.strip()
                    if s.startswith("description:"):
                        after = True
                        continue
                    if after and s and not s.endswith(":"):
                        return s.lstrip("-").strip()
        return desc

    def list_meta(self) -> List[Dict[str, str]]:
        """قائمة الأوامر الفريدة مع أوصافها (للإكمال التلقائي في الواجهات)."""
        best: Dict[str, tuple] = {}   # str(path) -> (name, desc)
        for name, path in self._commands.items():
            key = str(path)
            if key in best and len(best[key][0]) <= len(name):
                continue
            best[key] = (name, self._description_of(path))
        items = [{"name": n, "description": d} for (n, d) in best.values()]
        return sorted(items, key=lambda x: x["name"])

    def has(self, name: str) -> bool:
        return name in self._commands

    @staticmethod
    def _strip_frontmatter(text: str) -> Tuple[str, Dict[str, str]]:
        """فصل الـ frontmatter (بين ---) عن جسم الأمر"""
        meta: Dict[str, str] = {}
        if text.startswith("---"):
            m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
            if m:
                block, body = m.group(1), m.group(2)
                for line in block.splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        meta[k.strip()] = v.strip()
                return body.lstrip(), meta
        return text, meta

    def render(self, name: str, arguments: str = "") -> Optional[str]:
        """
        تحميل قالب الأمر واستبدال المتغيرات، وإرجاع البروموه الجاهز.
        يدعم: $ARGUMENTS و {{args}}.
        """
        path = self._commands.get(name)
        if path is None:
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception:
            return None
        body, _meta = self._strip_frontmatter(raw)
        body = body.replace("$ARGUMENTS", arguments).replace("{{args}}", arguments)
        return body.strip()

    def parse(self, text: str) -> Optional[Tuple[str, str]]:
        """
        تحويل إدخال المستخدم '/name args' إلى (name, args).
        يُرجع None إن لم يكن أمر سلاش معروفاً.
        """
        if not text.startswith("/"):
            return None
        parts = text[1:].split(maxsplit=1)
        if not parts:
            return None
        name = parts[0]
        args = parts[1] if len(parts) > 1 else ""
        if name not in self._commands:
            return None
        return name, args
