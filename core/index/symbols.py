"""
symbols.py — فهرس رموز الكود (symbol index) لـ WeaverCode 🕸️
============================================================
A lightweight symbol index over a project's source files, to speed up
navigation and understanding on large codebases: "where is function/class X
defined?" without a full-text scan every time.

  • Python  → parsed with the stdlib ``ast`` (accurate: functions, classes,
              methods, with line numbers and signatures)
  • JS/TS   → parsed with tolerant regexes (functions, classes, exported
              const arrows) — good enough for jump-to-definition

stdlib-only; the index is a plain dict that serializes to JSON and can be
cached under ~/.weaver/cache so re-indexing is only needed when files change.
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
            if ext in _PY_EXT or ext in _JS_EXT:
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


# JS/TS: أنماط متسامحة لالتقاط أكثر التعريفات شيوعاً
_JS_PATTERNS = [
    (re.compile(r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"), "class"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>"), "function"),
    (re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function"), "function"),
]


def extract_js(path: Path, rel: str) -> List[Dict]:
    """يستخرج رموز ملف JS/TS عبر regex (دوال/أصناف/const أسهُم مُصدَّرة)."""
    out: List[Dict] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return out
    for i, line in enumerate(lines, 1):
        for pat, kind in _JS_PATTERNS:
            m = pat.match(line)
            if m:
                out.append({"name": m.group(1), "kind": kind,
                            "file": rel, "line": i,
                            "signature": line.strip()[:120]})
                break
    return out


def build_index(root: str, cache: bool = True) -> Dict:
    """يبني فهرس رموز لمجلد مشروع ويُرجعه (ويحفظه في الكاش اختيارياً)."""
    root_path = Path(os.path.expanduser(root)).resolve()
    symbols: List[Dict] = []
    files_indexed = 0
    if root_path.is_file():
        source_files = [root_path]
        base = root_path.parent
    else:
        source_files = _iter_source_files(root_path)
        base = root_path
    for f in source_files:
        try:
            if f.stat().st_size > _MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        try:
            rel = str(f.relative_to(base))
        except ValueError:
            rel = str(f)
        ext = f.suffix.lower()
        if ext in _PY_EXT:
            found = extract_python(f, rel)
        elif ext in _JS_EXT:
            found = extract_js(f, rel)
        else:
            continue
        if found:
            files_indexed += 1
            symbols.extend(found)
    index = {
        "weavercode_symbol_index": 1,
        "root": str(root_path),
        "built_at": time.time(),
        "files": files_indexed,
        "count": len(symbols),
        "symbols": symbols,
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
