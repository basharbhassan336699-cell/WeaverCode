"""
loader.py — محمّل Skills لـ WeaverCode
يحمّل ملفات SKILL.md من .claude/skills/ ويتيحها كـ context قابل للحقن.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional


class SkillLoader:
    """
    يكتشف ملفات SKILL.md ويحمّلها.
    الصيغة: .claude/skills/<name>/SKILL.md
    أو:     .claude/skills/<name>.md
    """

    def __init__(self, skills_dir: Optional[Path] = None):
        root = Path(__file__).resolve().parent.parent.parent
        self.skills_dir = skills_dir or (root / ".claude" / "skills")
        self._skills: Dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        if not self.skills_dir.exists():
            return
        # البحث عن SKILL.md في مجلدات فرعية
        for skill_md in self.skills_dir.rglob("SKILL.md"):
            name = skill_md.parent.name
            try:
                content = skill_md.read_text(encoding="utf-8")
                self._skills[name] = self._strip_frontmatter(content)
            except Exception:
                continue
        # البحث عن ملفات .md مباشرة
        for skill_md in self.skills_dir.glob("*.md"):
            name = skill_md.stem
            if name not in self._skills:
                try:
                    content = skill_md.read_text(encoding="utf-8")
                    self._skills[name] = self._strip_frontmatter(content)
                except Exception:
                    continue

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        if text.startswith("---"):
            m = re.match(r"^---\s*\n.*?\n---\s*\n(.*)", text, re.DOTALL)
            if m:
                return m.group(1).strip()
        return text.strip()

    def names(self) -> List[str]:
        return sorted(self._skills.keys())

    def get(self, name: str) -> Optional[str]:
        return self._skills.get(name)

    def get_context(self, name: str) -> str:
        """إرجاع محتوى الـ skill جاهزاً للحقن في system prompt."""
        content = self._skills.get(name)
        if not content:
            return f"[Skill '{name}' غير موجود]"
        return f"## Skill: {name}\n\n{content}"

    def has(self, name: str) -> bool:
        return name in self._skills
