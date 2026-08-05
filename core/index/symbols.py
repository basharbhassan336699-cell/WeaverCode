"""
symbols.py — فهرس رموز الكود (symbol index) لـ WeaverCode 🕸️
============================================================
A lightweight symbol index over a project's source files, to speed up
navigation and understanding on large codebases: "where is function/class X
defined?" without a full-text scan every time.

  • Python        → parsed with the stdlib ``ast`` (accurate: functions,
                    classes, methods, with line numbers and signatures)
  • JS/TS/Go/     → parsed with tolerant regexes (functions, classes,
    Rust/Java       structs, interfaces, …) — good enough for jump-to-definition

stdlib-only; the index is a plain dict that serializes to JSON and can be
cached under ~/.weaver/cache so re-indexing is only needed when files change.
An *incremental* rebuild re-parses only files whose mtime changed, so it stays
fast on large codebases.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

# مجلدات لا نفهرسها أبداً (ضخمة أو غير مصدرية)
_SKIP_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", "node_modules", ".venv", "venv",
    "env", "dist", "build", ".mypy_cache", ".pytest_cache", ".weaver",
    ".idea", ".vscode", "site-packages", ".tox", "coverage", ".next",
}
_PY_EXT = {".py", ".pyi"}
_JS_EXT = {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"}
_GO_EXT = {".go"}
_RUST_EXT = {".rs"}
_JAVA_EXT = {".java"}
# كل الامتدادات المفهرَسة (Python عبر ast، والبقية عبر regex)
_ALL_EXT = _PY_EXT | _JS_EXT | _GO_EXT | _RUST_EXT | _JAVA_EXT
_MAX_FILE_BYTES = 1_500_000   # نتجاوز الملفات الضخمة (مولّدة عادةً)


def _cache_dir() -> Path:
    d = Path.home() / ".weaver" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _iter_source_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        # قلّم المجلدات المستبعَدة (تعديل in-place ليقلّم os.walk)
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS
                       and not d.startswith(".")]
        for fn in filenames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in _ALL_EXT:
                yield Path(dirpath) / fn


def _py_signature(node) -> str:
    """توقيع دالة Python مبسّط: الاسم + أسماء الوسائط."""
    try:
        a = node.args
        parts = [p.arg for p in getattr(a, "posonlyargs", [])]
        parts += [p.arg for p in a.args]
        if a.vararg:
            parts.append("*" + a.vararg.arg)
        parts += [p.arg for p in a.kwonlyargs]
        if a.kwarg:
            parts.append("**" + a.kwarg.arg)
        return f"{node.name}({', '.join(parts)})"
    except Exception:
        return node.name


def extract_python(path: Path, rel: str) -> List[Dict]:
    """يستخرج رموز ملف Python عبر ast (دوال/أصناف/طرق).

    زيارة واحدة واعية بالسياق: الدالة داخل صنف = «method»، وإلا = «function»،
    فلا يُحسب أي رمز مرّتين (بخلاف ast.walk الذي يزور العقدة نفسها مراراً)."""
    out: List[Dict] = []
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return out

    def visit(node, parent_class: Optional[str]):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if parent_class:
                    out.append({"name": child.name, "kind": "method",
                                "file": rel, "line": child.lineno,
                                "signature": f"{parent_class}.{_py_signature(child)}",
                                "parent": parent_class})
                else:
                    out.append({"name": child.name, "kind": "function",
                                "file": rel, "line": child.lineno,
                                "signature": _py_signature(child)})
                # دوال متداخلة داخل هذه الدالة = «function» (لا method)
                visit(child, None)
            elif isinstance(child, ast.ClassDef):
                out.append({"name": child.name, "kind": "class",
                            "file": rel, "line": child.lineno,
                            "signature": f"class {child.name}"})
                visit(child, child.name)
            else:
                visit(child, parent_class)

    visit(tree, None)
    return out


# أنماط متسامحة لكل لغة (regex سطرية) لالتقاط أكثر التعريفات شيوعاً
_JS_PATTERNS = [
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function"), "function"),
]
_GO_PATTERNS = [
    (re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\("), "function"),
    (re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+struct\b"), "struct"),
    (re.compile(r"^\s*type\s+([A-Za-z_]\w*)\s+interface\b"), "interface"),
]
_RUST_PATTERNS = [
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)"), "function"),
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+([A-Za-z_]\w*)"), "struct"),
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+([A-Za-z_]\w*)"), "enum"),
    (re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+([A-Za-z_]\w*)"), "trait"),
]
_JAVA_PATTERNS = [
    (re.compile(r"^\s*(?:public|private|protected)?\s*(?:abstract\s+|final\s+)?class\s+([A-Za-z_]\w*)"), "class"),
    (re.compile(r"^\s*(?:public|private|protected)?\s*interface\s+([A-Za-z_]\w*)"), "interface"),
    (re.compile(r"^\s*(?:public|private|protected)?\s*enum\s+([A-Za-z_]\w*)"), "enum"),
    (re.compile(r"^\s*(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?[\w<>\[\],\s]+?\s+([A-Za-z_]\w*)\s*\([^;{]*\)\s*\{"), "method"),
]

_REGEX_PATTERNS = {
    **{e: _JS_PATTERNS for e in _JS_EXT},
    **{e: _GO_PATTERNS for e in _GO_EXT},
    **{e: _RUST_PATTERNS for e in _RUST_EXT},
    **{e: _JAVA_PATTERNS for e in _JAVA_EXT},
}


def extract_regex(path: Path, rel: str, patterns: List) -> List[Dict]:
    """يستخرج رموز ملف نصّي عبر أنماط regex سطرية (JS/TS/Go/Rust/Java)."""
    out: List[Dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return out
    for i, line in enumerate(lines, 1):
        for pat, kind in patterns:
            m = pat.match(line)
            if m:
                out.append({"name": m.group(1), "kind": kind,
                            "file": rel, "line": i,
                            "signature": line.strip()[:120]})
                break
    return out


def extract_file(path: Path, rel: str) -> List[Dict]:
    """يوجّه الملف إلى المستخرِج المناسب حسب امتداده."""
    ext = path.suffix.lower()
    if ext in _PY_EXT:
        return extract_python(path, rel)
    patterns = _REGEX_PATTERNS.get(ext)
    if patterns:
        return extract_regex(path, rel, patterns)
    return []


def build_index(root: str, cache: bool = True,
                incremental: bool = False) -> Dict:
    """يبني فهرس رموز لمجلد مشروع ويُرجعه (ويحفظه في الكاش اختيارياً).

    incremental=True: يحمّل الفهرس المُخزَّن ويعيد تحليل الملفات المتغيّرة فقط
    (حسب mtime)، ويُسقِط رموز الملفات المحذوفة — أسرع كثيراً على المشاريع الكبيرة.
    يسقط تلقائياً إلى بناء كامل إن لم يوجد كاش سابق."""
    root_path = Path(os.path.expanduser(root)).resolve()
    if root_path.is_file():
        source_files = [root_path]
        base = root_path.parent
    else:
        source_files = _iter_source_files(root_path)
        base = root_path

    old = load_index(root) if incremental else None
    old_mtimes: Dict[str, float] = (old or {}).get("mtimes", {}) or {}
    old_by_file: Dict[str, List[Dict]] = {}
    if old:
        for s in old.get("symbols", []):
            old_by_file.setdefault(s["file"], []).append(s)

    symbols: List[Dict] = []
    mtimes: Dict[str, float] = {}
    files_indexed = 0
    reused = 0
    for f in source_files:
        try:
            st = f.stat()
            if st.st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        try:
            rel = str(f.relative_to(base))
        except ValueError:
            rel = str(f)
        mt = st.st_mtime
        mtimes[rel] = mt
        # إعادة استخدام رموز ملف لم يتغيّر (بناء تزايدي)
        if (incremental and rel in old_mtimes
                and abs(old_mtimes[rel] - mt) < 1e-6 and rel in old_by_file):
            symbols.extend(old_by_file[rel])
            files_indexed += 1
            reused += 1
            continue
        found = extract_file(f, rel)
        if found:
            files_indexed += 1
            symbols.extend(found)
    index = {
        "weavercode_symbol_index": 1,
        "root": str(root_path),
        "built_at": time.time(),
        "files": files_indexed,
        "count": len(symbols),
        "reused_files": reused,
        "symbols": symbols,
        "mtimes": mtimes,
    }
    if cache:
        try:
            save_index(index)
        except Exception:
            pass
    return index


def _cache_file(root: str) -> Path:
    h = hashlib.sha1(str(Path(os.path.expanduser(root)).resolve())
                     .encode("utf-8")).hexdigest()[:16]
    return _cache_dir() / f"symbols-{h}.json"


def save_index(index: Dict) -> Path:
    path = _cache_file(index["root"])
    path.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return path


def load_index(root: str) -> Optional[Dict]:
    """يحمّل فهرساً محفوظاً من الكاش (أو None إن لم يوجد)."""
    path = _cache_file(root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find(index: Dict, name: str, limit: int = 20) -> List[Dict]:
    """يبحث عن رمز بالاسم (مطابقة دقيقة أولاً ثم جزئية غير حسّاسة للحالة)."""
    syms = index.get("symbols", [])
    low = name.lower()
    exact = [s for s in syms if s["name"] == name]
    partial = [s for s in syms
               if s["name"] != name and low in s["name"].lower()]
    return (exact + partial)[:limit]


def outline(index: Dict, file_rel: str) -> List[Dict]:
    """رموز ملف واحد مرتّبة بالسطر (مخطّط الملف)."""
    syms = [s for s in index.get("symbols", []) if s["file"] == file_rel]
    return sorted(syms, key=lambda s: s["line"])
