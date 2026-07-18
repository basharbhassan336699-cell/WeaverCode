"""
claude_md.py — تحميل ملفات CLAUDE.md المتداخلة لـ WeaverCode
============================================================

يكتشف ملفات `CLAUDE.md` (و`CLAUDE.local.md`) في:
  - جذر المشروع
  - المجلدات الأب (حتى جذر الملفات)
  - المجلدات الفرعية داخل مساحة العمل

ثم يدمجها في كتلة سياق واحدة تُضاف للبروموه النظامي — تماماً كما تفعل
Claude Code مع تعليمات المشروع المتداخلة.

القواعد:
    - الأقرب للجذر أولاً ثم الأعمق (ترتيب مستقر).
    - تجاهل المجلدات الضخمة/المخفية الشائعة (node_modules, .git, ...).
    - حدّ لعدد الملفات وحجم كل ملف لتفادي إغراق السياق.

EN: Discovers nested CLAUDE.md / CLAUDE.local.md instruction files across the
workspace (root, ancestors, and subdirectories) and merges them into one
context block for the system prompt — mirroring Claude Code's nested project
instructions.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

_NAMES = ("CLAUDE.md", "CLAUDE.local.md")

# مجلدات تُتخطّى أثناء البحث في العمق
_SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".next", ".cache",
    "site-packages", ".tox", ".idea", ".vscode", "vendor", "target",
}

# حدود لتفادي إغراق السياق
_MAX_FILES = 12
_MAX_FILE_CHARS = 12_000
_MAX_DEPTH = 4


def _ancestors_with_root(start: Path, root: Path) -> List[Path]:
    """المجلدات من root نزولاً حتى start (شاملة)، بترتيب من الأعلى للأسفل."""
    start = start.resolve()
    root = root.resolve()
    chain: List[Path] = []
    cur = start
    while True:
        chain.append(cur)
        if cur == root or cur.parent == cur:
            break
        cur = cur.parent
    chain.reverse()
    # نضمن أن root ضمن السلسلة حتى لو لم يكن start تحته
    if root not in chain:
        chain.insert(0, root)
    return chain


def discover(work_dir: str,
             extra_dirs: Optional[List[str]] = None,
             include_ancestors: bool = True) -> List[Path]:
    """
    يكتشف كل ملفات CLAUDE.md ذات الصلة.

    Returns: قائمة مسارات مرتّبة (بلا تكرار)، الأقرب للجذر أولاً.
    """
    root = Path(work_dir).resolve()
    found: List[Path] = []
    seen: set = set()

    def _add(p: Path):
        rp = p.resolve()
        if rp.exists() and rp.is_file() and rp not in seen:
            seen.add(rp)
            found.append(rp)

    # (1) ملفات المجلدات الأب (للسياق الموروث)
    if include_ancestors:
        # نبحث من نظام الملفات الأعلى نزولاً حتى work_dir
        cur = root
        ancestors: List[Path] = []
        while True:
            ancestors.append(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
        ancestors.reverse()
        for d in ancestors:
            for name in _NAMES:
                _add(d / name)

    # (2) البحث في العمق داخل work_dir والمجلدات الإضافية
    roots = [root]
    for extra in (extra_dirs or []):
        try:
            ep = Path(extra).resolve()
            if ep.exists() and ep not in roots:
                roots.append(ep)
        except Exception:
            continue

    for base in roots:
        _walk(base, base, 0, _add)

    return found[:_MAX_FILES]


def _walk(base: Path, current: Path, depth: int, add_fn) -> None:
    """مسح تكراري محدود العمق يضيف ملفات CLAUDE.md المكتشفة."""
    for name in _NAMES:
        add_fn(current / name)
    if depth >= _MAX_DEPTH:
        return
    try:
        entries = list(current.iterdir())
    except (OSError, PermissionError):
        return
    for entry in entries:
        if not entry.is_dir():
            continue
        if entry.name in _SKIP_DIRS or entry.name.startswith("."):
            continue
        _walk(base, entry, depth + 1, add_fn)


def load_nested_context(work_dir: str,
                        extra_dirs: Optional[List[str]] = None,
                        root_md: Optional[str] = None) -> str:
    """
    يبني كتلة سياق نصّية من كل ملفات CLAUDE.md المكتشفة.

    Args:
        work_dir: مجلد العمل الأساسي.
        extra_dirs: مجلدات عمل إضافية (multi-workspace).
        root_md: مسار CLAUDE.md الجذري الذي حُمّل مسبقاً (يُستثنى لتفادي التكرار).

    Returns: نص مدموج (فارغ إن لم يوجد شيء إضافي).
    """
    files = discover(work_dir, extra_dirs)
    skip = set()
    if root_md:
        try:
            skip.add(Path(root_md).resolve())
        except Exception:
            pass

    blocks: List[str] = []
    for f in files:
        if f.resolve() in skip:
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            continue
        if not text:
            continue
        if len(text) > _MAX_FILE_CHARS:
            text = text[:_MAX_FILE_CHARS] + "\n… (اقتُطع)"
        # مسار مختصر نسبةً لمجلد العمل إن أمكن
        try:
            rel = f.relative_to(Path(work_dir).resolve())
            label = str(rel)
        except ValueError:
            label = str(f)
        blocks.append(f"### 📁 `{label}`\n{text}")

    if not blocks:
        return ""
    return ("## تعليمات المشروع المتداخلة (CLAUDE.md)\n\n"
            + "\n\n".join(blocks))
