"""
action_blocks.py — نظام Action Blocks لـ WeaverCode
====================================================

يُتتبع كل عمليات الأدوات في جولة وكيلية واحدة ويُلخّصها في سطر واحد
بصيغة مشابهة لـ Claude Code:

    ‹ 1- +11  Edited a file, read a file
    ‹ 2- +2   Ran a command, edited 2 files
    ‹ 0- +135 Created a file, ran a command
    ‹ Creating build.js ...   ← حالة في التنفيذ

المصطلحات:
    lines_removed  عدد الأسطر المحذوفة في عمليات الكتابة (باللون الأحمر)
    lines_added    عدد الأسطر المضافة في عمليات الكتابة (باللون الأخضر)
    operations     قائمة بأسماء العمليات المنجزة بالترتيب
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


# ── تصنيف الأدوات إلى فئات عمليات ─────────────────────────────────────────

# كل أداة → (اسم عملية مفردة، اسم عملية تعددية، هل لها diff؟)
_TOOL_META = {
    # ملفات
    "Read":          ("read a file",      "read {n} files",       False),
    "Write":         ("created a file",   "created {n} files",    True),
    "Edit":          ("edited a file",    "edited {n} files",     True),
    "MultiEdit":     ("edited a file",    "edited {n} files",     True),
    # أوامر
    "Bash":          ("ran a command",    "ran {n} commands",     False),
    "PythonRun":     ("ran a script",     "ran {n} scripts",      False),
    "PipInstall":    ("installed package", "installed {n} packages", False),
    # بحث
    "Glob":          ("searched files",   "searched files",       False),
    "Grep":          ("searched content", "searched content",     False),
    "DirectoryList": ("listed directory", "listed directories",   False),
    # ويب
    "WebFetch":      ("fetched a URL",    "fetched {n} URLs",     False),
    "WebSearch":     ("searched web",     "searched web",         False),
    # ذاكرة
    "MemorySave":    ("saved to memory",  "saved to memory",      False),
    "MemorySearch":  ("searched memory",  "searched memory",      False),
    "MemoryDelete":  ("deleted memory",   "deleted memory",       False),
    "MemoryList":    ("listed memory",    "listed memory",        False),
    # مهام
    "TaskCreate":    ("created a task",   "created {n} tasks",    False),
    "TaskList":      ("listed tasks",     "listed tasks",         False),
    "TaskUpdate":    ("updated a task",   "updated {n} tasks",    False),
    # git
    "GitStatus":     ("checked git",      "checked git",          False),
    "GitClone":      ("cloned a repo",    "cloned {n} repos",     False),
    "GitCommit":     ("made a commit",    "made {n} commits",     False),
    "GitPush":       ("pushed to remote", "pushed to remote",     False),
    # GitHub
    "GitHubCreateRepo":  ("created repo",   "created {n} repos",   False),
    "GitHubListRepos":   ("listed repos",   "listed repos",        False),
    "GitHubCreateIssue": ("created issue",  "created {n} issues",  False),
    "GitHubStatus":      ("checked GitHub", "checked GitHub",      False),
    # جدولة
    "CronCreate":    ("scheduled task",   "scheduled {n} tasks",  False),
    "CronList":      ("listed cron",      "listed cron",          False),
    "CronDelete":    ("deleted cron",     "deleted cron",         False),
    # أخرى
    "Monitor":       ("monitored",        "monitored",            False),
    "LSP":           ("checked syntax",   "checked syntax",       False),
    "AskUser":       ("asked user",       "asked user",           False),
    "Agent":         ("ran sub-agent",    "ran {n} sub-agents",   False),
    "EnterPlanMode": ("entered plan mode", "entered plan mode",   False),
    "ExitPlanMode":  ("submitted plan",   "submitted plan",       False),
    "EnvSet":        ("set env var",      "set {n} env vars",     False),
    "EnvGet":        ("got env var",      "got {n} env vars",     False),
    "Skill":         ("loaded skill",     "loaded {n} skills",    False),
}

_DEFAULT_META = ("used a tool", "used {n} tools", False)


def _get_meta(tool_name: str) -> Tuple[str, str, bool]:
    return _TOOL_META.get(tool_name, _DEFAULT_META)


# ── بنية بيانات الـ Action Block الواحد ────────────────────────────────────

@dataclass
class ToolOp:
    """عملية أداة واحدة مكتملة."""
    tool_name:     str
    args:          dict
    result:        str
    lines_removed: int = 0
    lines_added:   int = 0
    in_progress:   bool = False   # True = لا يزال يُنفَّذ

    @property
    def primary_arg(self) -> str:
        """أهم وسيط للعرض: المسار أو الأمر أو الاستعلام."""
        a = self.args
        return (a.get("path") or a.get("command") or a.get("query")
                or a.get("url") or a.get("pattern") or "")

    @property
    def display_name(self) -> str:
        """اسم العرض للعملية (مفردة)."""
        return _get_meta(self.tool_name)[0]


@dataclass
class ActionBlock:
    """
    ملخص جولة وكيلية واحدة — يجمع عمليات أدوات متعددة.

    يُعرض بعد انتهاء الجولة بصيغة:
        ‹ 1- +11  Edited a file, read a file
    """
    ops:           List[ToolOp] = field(default_factory=list)
    in_progress:   bool = False   # True = الجولة لا تزال تعمل
    active_tool:   str = ""       # اسم الأداة الجارية حالياً
    active_arg:    str = ""       # وسيطها الأساسي

    # ── إحصاءات مجمّعة ─────────────────────────────────────────────────────

    @property
    def lines_removed(self) -> int:
        return sum(op.lines_removed for op in self.ops)

    @property
    def lines_added(self) -> int:
        return sum(op.lines_added for op in self.ops)

    @property
    def has_diff(self) -> bool:
        return self.lines_removed > 0 or self.lines_added > 0

    # ── بناء جملة الوصف ────────────────────────────────────────────────────

    def _build_description(self) -> str:
        """
        يبني جملة الوصف بتجميع الأدوات المتكررة:
            [Edit×3, Read×1, Bash×2] → "Edited 3 files, read a file, ran 2 commands"
        """
        if not self.ops:
            return "ran a tool"

        # عدّ تكرار كل أداة بالترتيب (مع الحفاظ على التسلسل الأول)
        seen: dict = {}
        for op in self.ops:
            seen[op.tool_name] = seen.get(op.tool_name, 0) + 1

        parts = []
        done = set()
        for op in self.ops:
            t = op.tool_name
            if t in done:
                continue
            done.add(t)
            n = seen[t]
            singular, plural, _ = _get_meta(t)
            if n == 1:
                parts.append(singular)
            else:
                parts.append(plural.replace("{n}", str(n)))

        # ربط الأجزاء: "A, B, and C"
        if len(parts) == 1:
            return parts[0]
        if len(parts) == 2:
            return f"{parts[0]}, {parts[1]}"
        return ", ".join(parts[:-1]) + f", {parts[-1]}"

    def summary_line(self) -> str:
        """
        السطر الكامل للعرض — بدون ألوان (الألوان تُضاف في draw_action_block).
        مثال: "1- +11  Edited a file, read a file"
        """
        removed = self.lines_removed
        added = self.lines_added
        desc = self._build_description()

        if self.has_diff:
            return f"{removed}- +{added}  {desc}"
        else:
            return desc

    def in_progress_line(self) -> str:
        """
        سطر الحالة أثناء التنفيذ.
        مثال: "Creating build.js ..."
        """
        if not self.active_tool:
            return "جارٍ التنفيذ..."
        arg = Path(self.active_arg).name if self.active_arg else ""
        _PROGRESSIVE = {
            "Write":      "Creating",
            "Edit":       "Editing",
            "MultiEdit":  "Editing",
            "Read":       "Reading",
            "Bash":       "Running",
            "PythonRun":  "Running",
            "Glob":       "Searching",
            "Grep":       "Searching",
            "WebFetch":   "Fetching",
            "WebSearch":  "Searching",
            "GitClone":   "Cloning",
            "GitCommit":  "Committing",
            "GitPush":    "Pushing",
            "PipInstall": "Installing",
            "Agent":      "Running sub-agent",
            "MemorySave": "Saving",
            "TaskCreate": "Creating task",
        }
        verb = _PROGRESSIVE.get(self.active_tool, "Running")
        return f"{verb} {arg} ..." if arg else f"{verb} ..."


# ── متتبع الجولة الوكيلية الواحدة ───────────────────────────────────────────

class ActionBlockTracker:
    """
    يُجمع عمليات جولة وكيلية واحدة ويُنتج ActionBlock منها.

    الاستخدام في query_engine:
        tracker = ActionBlockTracker()
        tracker.begin_tool("Write", {"path": "build.js"})   # قبل التنفيذ
        ...تنفيذ الأداة...
        tracker.end_tool("Write", args, result)              # بعد التنفيذ
        block = tracker.finalize()                           # نهاية الجولة
    """

    def __init__(self):
        self._block = ActionBlock()

    def begin_tool(self, tool_name: str, args: dict) -> None:
        """يُسجَّل قبل بدء التنفيذ — يُحدّث حالة in_progress."""
        args = args or {}
        primary = (args.get("path") or args.get("command") or
                   args.get("query") or args.get("url") or
                   args.get("pattern") or "")
        self._block.in_progress = True
        self._block.active_tool = tool_name
        self._block.active_arg = str(primary)

    def end_tool(self, tool_name: str, args: dict, result: str) -> ToolOp:
        """يُسجَّل بعد انتهاء التنفيذ — يُحسب الـ diff ويُضاف للعمليات."""
        args = args or {}
        removed, added = _compute_diff(tool_name, args, result)
        op = ToolOp(
            tool_name=tool_name,
            args=args,
            result=result,
            lines_removed=removed,
            lines_added=added,
        )
        self._block.ops.append(op)
        self._block.active_tool = ""
        self._block.active_arg = ""
        return op

    def finalize(self) -> ActionBlock:
        """إنهاء الجولة وإرجاع الـ ActionBlock النهائي."""
        self._block.in_progress = False
        block = self._block
        self._block = ActionBlock()  # تهيئة جديدة للجولة التالية
        return block

    def current_block(self) -> ActionBlock:
        return self._block


# ── حساب الـ diff ────────────────────────────────────────────────────────────

def _compute_diff(tool_name: str, args: dict,
                  result: str) -> Tuple[int, int]:
    """
    يحسب عدد الأسطر المحذوفة والمضافة لأدوات الكتابة.

    للـ Write: removed = 0, added = عدد أسطر المحتوى
    للـ Edit:  removed = أسطر old_string, added = أسطر new_string
    للـ MultiEdit: مجموع كل الاستبدالات
    للـ Bash:  removed = 0, added = 0 (لا diff)
    """
    _, _, has_diff = _get_meta(tool_name)
    if not has_diff:
        return 0, 0

    if tool_name == "Write":
        content = args.get("content", "")
        return 0, content.count("\n") + (1 if content else 0)

    if tool_name == "Edit":
        old = args.get("old_string", "")
        new = args.get("new_string", "")
        replace_all = args.get("replace_all", False)
        # إذا replace_all، نحاول تقدير العدد من نتيجة الأداة
        multiplier = 1
        if replace_all and result:
            m = re.search(r"(\d+)\s*مرات?|replaced\s*(\d+)", result)
            if m:
                multiplier = int(m.group(1) or m.group(2) or 1)
        r = old.count("\n") + (1 if old else 0)
        a = new.count("\n") + (1 if new else 0)
        return r * multiplier, a * multiplier

    if tool_name == "MultiEdit":
        edits = args.get("edits", [])
        total_r, total_a = 0, 0
        for ed in edits:
            old = ed.get("old_string", "")
            new = ed.get("new_string", "")
            total_r += old.count("\n") + (1 if old else 0)
            total_a += new.count("\n") + (1 if new else 0)
        return total_r, total_a

    return 0, 0
