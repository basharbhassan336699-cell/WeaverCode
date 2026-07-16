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
