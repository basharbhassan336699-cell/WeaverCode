"""
diff_preview.py — معاينة الفروق قبل تنفيذ عمليات الكتابة في WeaverCode
======================================================================

يولّد معاينة unified diff لعمليات Write / Edit / MultiEdit *قبل* كتابتها
على القرص، حتى يرى المستخدم بالضبط ما سيتغيّر — كما في Claude Code.

    +  السطر مضاف   (أخضر)
    -  السطر محذوف  (أحمر)

الاستخدام:
    preview = preview_change("Edit", {"path": "a.py",
                                      "old_string": "...",
                                      "new_string": "..."})
    print(preview.colored())     # للطرفية
    counts = (preview.added, preview.removed)

EN: Builds a unified-diff preview for Write/Edit/MultiEdit *before* the
change hits disk, so the caller (CLI/web) can show the user what will
change. Pure/read-only: it never writes files.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

# ألوان ANSI للطرفية
_GRN = "\033[32m"
_RED = "\033[31m"
_GRY = "\033[90m"
_CYA = "\033[36m"
_RST = "\033[0m"

# حد أقصى لعدد أسطر الـ diff المعروضة (تفادي الإغراق)
_MAX_DIFF_LINES = 400


@dataclass
class DiffPreview:
    """نتيجة معاينة فرق لعملية كتابة واحدة."""
    path: str
    is_new: bool = False
    lines: List[str] = field(default_factory=list)  # أسطر unified diff (بلا ألوان)
    added: int = 0
    removed: int = 0
    error: str = ""
    truncated: bool = False

    @property
    def has_changes(self) -> bool:
        return self.added > 0 or self.removed > 0 or self.is_new

    def stat_line(self) -> str:
        """سطر إحصائي مختصر: 'a.py  +12 -3'."""
        tag = " (ملف جديد)" if self.is_new else ""
        return f"{self.path}{tag}  +{self.added} -{self.removed}"

    def plain(self) -> str:
        """نص الـ diff بلا ألوان."""
        if self.error:
            return f"[تعذّر توليد المعاينة: {self.error}]"
        body = "\n".join(self.lines)
        if self.truncated:
            body += "\n… (اقتُطعت المعاينة)"
        return body

    def colored(self) -> str:
        """نص الـ diff بألوان ANSI للطرفية."""
        if self.error:
            return f"{_GRY}[تعذّر توليد المعاينة: {self.error}]{_RST}"
        out: List[str] = []
        for ln in self.lines:
            if ln.startswith("+") and not ln.startswith("+++"):
                out.append(f"{_GRN}{ln}{_RST}")
            elif ln.startswith("-") and not ln.startswith("---"):
                out.append(f"{_RED}{ln}{_RST}")
            elif ln.startswith("@@"):
                out.append(f"{_CYA}{ln}{_RST}")
            elif ln.startswith(("+++", "---")):
                out.append(f"{_GRY}{ln}{_RST}")
            else:
                out.append(ln)
        body = "\n".join(out)
        if self.truncated:
            body += f"\n{_GRY}… (اقتُطعت المعاينة){_RST}"
        return body


def _unified(old: str, new: str, path: str) -> DiffPreview:
    """يبني DiffPreview من نصّين."""
    old_lines = old.splitlines(keepends=False)
    new_lines = new.splitlines(keepends=False)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{path}", tofile=f"b/{path}",
        lineterm="",
    ))
    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    truncated = False
    if len(diff) > _MAX_DIFF_LINES:
        diff = diff[:_MAX_DIFF_LINES]
        truncated = True
    return DiffPreview(path=path, lines=diff, added=added,
                       removed=removed, truncated=truncated)


def _compute_new_content(tool_name: str, args: Dict[str, Any],
                         old: str) -> Optional[str]:
    """يحسب المحتوى الجديد المتوقّع دون كتابته على القرص."""
    if tool_name == "Write":
        return args.get("content", "")

    if tool_name == "Edit":
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        if old_string not in old:
            return None
        if replace_all:
            return old.replace(old_string, new_string)
        return old.replace(old_string, new_string, 1)

    if tool_name == "MultiEdit":
        content = old
        for ed in args.get("edits", []):
            o = ed.get("old_string", "")
            n = ed.get("new_string", "")
            if o not in content:
                return None
            if ed.get("replace_all", False):
                content = content.replace(o, n)
            else:
                content = content.replace(o, n, 1)
        return content

    return None


def preview_change(tool_name: str, args: Dict[str, Any]) -> DiffPreview:
    """
    يولّد معاينة فرق لعملية كتابة قبل تنفيذها.

    يدعم: Write / Edit / MultiEdit. لأي أداة أخرى → DiffPreview فارغ.
    لا يكتب أي شيء على القرص.
    """
    path = args.get("path", "")
    if tool_name not in ("Write", "Edit", "MultiEdit") or not path:
        return DiffPreview(path=path or "", error="أداة غير مدعومة للمعاينة")

    p = Path(path)
    is_new = not p.exists()
    old = ""
    if not is_new:
        try:
            old = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return DiffPreview(path=path, error=str(e))

    new = _compute_new_content(tool_name, args, old)
    if new is None:
        return DiffPreview(path=path,
                           error="لم يُعثر على النص المطلوب استبداله")

    preview = _unified(old, new, path)
    preview.is_new = is_new
    return preview


def is_previewable(tool_name: str) -> bool:
    """هل يمكن معاينة فرق هذه الأداة؟"""
    return tool_name in ("Write", "Edit", "MultiEdit")
