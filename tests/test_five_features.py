"""
test_five_features.py — اختبارات الميزات الخمس المضافة
======================================================
1) TodoWrite + NotebookEdit tools
2) @-mention file syntax
3) Diff preview
4) Multimodal Read (images/PDF)
5) Plugin settings parsing
"""

import base64
import json
from pathlib import Path

import pytest

from core.tools.registry import ToolRegistry
from core.mentions import expand_mentions, find_mentions
from core.diff_preview import preview_change, is_previewable
from core import multimodal
from core.plugins.settings import (
    parse_settings_text, parse_frontmatter, split_frontmatter,
    load_plugin_settings,
)


# ── 1) TodoWrite ────────────────────────────────────────────────────────────

def test_todowrite_formats_and_stores():
    reg = ToolRegistry()
    out = reg._todo_write([
        {"content": "اكتب الكود", "status": "completed"},
        {"content": "شغّل الاختبار", "status": "in_progress",
         "activeForm": "تشغيل الاختبار"},
        {"content": "انشر", "status": "pending"},
    ])
    assert "☑" in out and "▶" in out and "☐" in out
    assert "تشغيل الاختبار" in out       # activeForm يظهر للجاري
    assert "(1/3 مكتملة)" in out
    assert len(reg.get_todos()) == 3


def test_todowrite_filters_invalid():
    reg = ToolRegistry()
    reg._todo_write([{"content": "", "status": "pending"},
                     {"content": "صالح", "status": "bad"}])
    todos = reg.get_todos()
    assert len(todos) == 1
    assert todos[0]["status"] == "pending"   # حالة غير صالحة → pending


# ── 1) NotebookEdit ─────────────────────────────────────────────────────────

def _make_nb(tmp_path) -> Path:
    nb = {
        "cells": [
            {"cell_type": "code", "id": "a1", "source": ["print(1)\n"],
             "metadata": {}, "outputs": [], "execution_count": None},
        ],
        "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
    }
    p = tmp_path / "nb.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")
    return p


def test_notebook_replace(tmp_path):
    reg = ToolRegistry()
    p = _make_nb(tmp_path)
    out = reg._notebook_edit(str(p), cell_id="a1", new_source="print(2)\n")
    assert "✅" in out
    nb = json.loads(p.read_text(encoding="utf-8"))
    assert "".join(nb["cells"][0]["source"]) == "print(2)\n"


def test_notebook_insert_and_delete(tmp_path):
    reg = ToolRegistry()
    p = _make_nb(tmp_path)
    reg._notebook_edit(str(p), cell_id="a1", new_source="# hi",
                       cell_type="markdown", edit_mode="insert")
    nb = json.loads(p.read_text(encoding="utf-8"))
    assert len(nb["cells"]) == 2
    assert nb["cells"][1]["cell_type"] == "markdown"

    reg._notebook_edit(str(p), cell_id="0", edit_mode="delete")
    nb = json.loads(p.read_text(encoding="utf-8"))
    assert len(nb["cells"]) == 1


def test_notebook_missing_file():
    reg = ToolRegistry()
    out = reg._notebook_edit("/nonexistent/x.ipynb", cell_id="0")
    assert "غير موجود" in out


# ── 2) @-mention ────────────────────────────────────────────────────────────

def test_find_mentions_basic():
    m = find_mentions("راجع @core/a.py و @b.txt")
    assert m == ["core/a.py", "b.txt"]


def test_expand_mentions_injects_existing(tmp_path):
    f = tmp_path / "hello.py"
    f.write_text("print('hi')\n", encoding="utf-8")
    text = f"اشرح @{f.name}"
    out, injected = expand_mentions(text, base_dir=tmp_path)
    assert injected == [f.name]
    assert "print('hi')" in out
    assert "الملفات المُشار إليها" in out


def test_expand_mentions_ignores_missing(tmp_path):
    out, injected = expand_mentions("راجع @nope.py", base_dir=tmp_path)
    assert injected == []
    assert out == "راجع @nope.py"


def test_expand_mentions_ignores_email(tmp_path):
    # user@host مسبوق بحرف → ليس mention
    out, injected = expand_mentions("راسلني على user@host.com", base_dir=tmp_path)
    assert injected == []


# ── 3) Diff preview ─────────────────────────────────────────────────────────

def test_preview_write_new_file(tmp_path):
    p = tmp_path / "new.txt"
    pv = preview_change("Write", {"path": str(p), "content": "a\nb\nc"})
    assert pv.is_new
    assert pv.added == 3
    assert pv.has_changes


def test_preview_edit_counts(tmp_path):
    p = tmp_path / "e.txt"
    p.write_text("line1\nline2\nline3\n", encoding="utf-8")
    pv = preview_change("Edit", {"path": str(p),
                                 "old_string": "line2",
                                 "new_string": "LINE2\nEXTRA"})
    assert pv.added >= 1 and pv.removed >= 1
    assert "LINE2" in pv.plain()


def test_preview_edit_not_found(tmp_path):
    p = tmp_path / "e.txt"
    p.write_text("abc", encoding="utf-8")
    pv = preview_change("Edit", {"path": str(p),
                                 "old_string": "zzz", "new_string": "q"})
    assert pv.error


def test_preview_unsupported_tool():
    assert not is_previewable("Bash")
    pv = preview_change("Bash", {"command": "ls"})
    assert pv.error


# ── 4) Multimodal ───────────────────────────────────────────────────────────

# أصغر PNG صالح (1x1 شفاف)
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_detect_media_type():
    assert multimodal.detect_media_type("a.png") == "image/png"
    assert multimodal.detect_media_type("a.jpeg") == "image/jpeg"
    assert multimodal.detect_media_type("a.pdf") == "application/pdf"
    assert multimodal.detect_media_type("a.txt") is None


def test_anthropic_and_openai_blocks(tmp_path):
    img = tmp_path / "x.png"
    img.write_bytes(_PNG_1x1)
    a = multimodal.build_anthropic_block(str(img))
    assert a["type"] == "image"
    assert a["source"]["media_type"] == "image/png"
    assert a["source"]["data"]
    o = multimodal.build_openai_block(str(img))
    assert o["type"] == "image_url"
    assert o["image_url"]["url"].startswith("data:image/png;base64,")


def test_read_tool_describes_image(tmp_path):
    reg = ToolRegistry()
    img = tmp_path / "pic.png"
    img.write_bytes(_PNG_1x1)
    out = reg._read(str(img))
    assert "صورة" in out
    assert "image/png" in out
    # لا يحاول قراءته كنص
    assert "print" not in out


# ── 5) Plugin settings ──────────────────────────────────────────────────────

_SETTINGS = """---
enabled: true
max_value: 42
ratio: 0.5
label: "value with spaces"
tags: ["a", "b", "c"]
# comment line
empty:
---

# Body

نص حر.
"""


def test_split_and_parse_frontmatter():
    fm, body = split_frontmatter(_SETTINGS)
    assert "enabled: true" in fm
    assert "# Body" in body
    data = parse_frontmatter(fm)
    assert data["enabled"] is True
    assert data["max_value"] == 42
    assert data["ratio"] == 0.5
    assert data["label"] == "value with spaces"
    assert data["tags"] == ["a", "b", "c"]
    assert data["empty"] == ""


def test_parse_settings_text_body():
    parsed = parse_settings_text(_SETTINGS)
    assert parsed["settings"]["enabled"] is True
    assert "نص حر" in parsed["body"]


def test_no_frontmatter_returns_empty():
    parsed = parse_settings_text("just text, no frontmatter")
    assert parsed["settings"] == {}
    assert parsed["body"] == "just text, no frontmatter"


def test_load_plugin_settings_from_project(tmp_path):
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "myplugin.local.md").write_text(
        "---\nenabled: false\nthreshold: 7\n---\n", encoding="utf-8")
    settings = load_plugin_settings("myplugin", project_root=tmp_path)
    assert settings["enabled"] is False
    assert settings["threshold"] == 7


def test_load_plugin_settings_missing(tmp_path):
    assert load_plugin_settings("nope", project_root=tmp_path) == {}
