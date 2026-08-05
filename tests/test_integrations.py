"""
test_integrations.py — اختبارات جسور الأدوات المدمجة (integrations/)
====================================================================
- OCR: detect_file_type + مسارات الأخطاء (بلا تشغيل النماذج الثقيلة).
- Loop: audit_project / check_gate / check_context (تتطلّب Node — تُتخطّى إن غاب).
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

import integrations
from integrations import (
    OcrBridgeError, LoopBridgeError,
    detect_file_type, run_olmocr, run_chandra,
    audit_project, check_gate, check_context,
)

_HAS_NODE = shutil.which("node") is not None
_needs_node = pytest.mark.skipif(not _HAS_NODE, reason="Node.js غير مثبّت")


# ── واجهة الحزمة ──────────────────────────────────────────────────────────────

def test_all_functions_exposed():
    for name in ("run_olmocr", "run_chandra", "detect_file_type",
                 "audit_project", "check_gate", "check_context"):
        assert hasattr(integrations, name), f"{name} غير معروض"


# ── الكشف عن نوع الملف ────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,tool,category", [
    ("/x/doc.pdf", "olmocr", "pdf"),
    ("/x/scan.PDF", "olmocr", "pdf"),
    ("/x/img.png", "chandra", "image"),
    ("/x/photo.jpeg", "chandra", "image"),
    ("/x/pic.tiff", "chandra", "image"),
    ("/x/notes.txt", None, "unsupported"),
    ("/x/data.csv", None, "unsupported"),
])
def test_detect_file_type(path, tool, category):
    r = detect_file_type(path)
    assert r["tool"] == tool
    assert r["category"] == category


# ── مسارات أخطاء OCR (لا تشغيل فعلي للنماذج) ─────────────────────────────────

def test_olmocr_missing_file():
    with pytest.raises(OcrBridgeError):
        run_olmocr("/nope/x.pdf", tempfile.mkdtemp(), "http://localhost:8000/v1")


def test_olmocr_requires_server(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(OcrBridgeError):
        run_olmocr(str(f), str(tmp_path / "ws"), "")   # بلا server_url


def test_chandra_missing_file():
    with pytest.raises(OcrBridgeError):
        run_chandra("/nope/x.png")


def test_chandra_bad_method(tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG\r\n")
    with pytest.raises(OcrBridgeError):
        run_chandra(str(f), method="banana")


# ── Loop: تتطلّب Node (تُتخطّى إن غاب) ───────────────────────────────────────

@_needs_node
def test_audit_project(tmp_path):
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    r = audit_project(str(tmp_path))
    assert r["tool"] == "loop-audit"
    assert isinstance(r["report"], dict)
    # التقرير يحوي درجة/مستوى
    assert "score" in r["report"] and "level" in r["report"]


@_needs_node
def test_check_gate_pass(tmp_path):
    r = check_gate(["src/app.py", "README.md"], action="commit")
    assert r["tool"] == "loop-gate"
    assert r["verdict"] in ("pass", "fail")
    assert isinstance(r["passed"], bool)
    # commit لملفات عادية ضمن السياسة → مسموح
    assert r["passed"] is True


@_needs_node
def test_check_gate_accepts_string_and_list(tmp_path):
    a = check_gate("a.py,b.py", action="commit")
    b = check_gate(["a.py", "b.py"], action="commit")
    assert a["passed"] == b["passed"]


def test_check_gate_requires_files():
    with pytest.raises(LoopBridgeError):
        check_gate([], action="commit")


@_needs_node
def test_check_context_continue(tmp_path):
    led = tmp_path / "ledger.json"
    led.write_text(json.dumps({
        "goal": "fix the failing test",
        "attempts": [{"summary": "first try", "outcome": "in-progress"}],
    }), encoding="utf-8")
    r = check_context(str(led))
    assert r["tool"] == "loop-context"
    assert r["decision"] in ("continue", "escalate")


def test_check_context_missing_ledger():
    with pytest.raises(LoopBridgeError):
        check_context("/nonexistent/ledger.json")


# ── سلامة الأدوات المدمجة ────────────────────────────────────────────────────

def test_vendors_present():
    root = Path(__file__).resolve().parent.parent / "vendors"
    for tool in ("olmocr", "chandra", "loop"):
        assert (root / tool).is_dir(), f"vendors/{tool} مفقود"
    assert (root / "__init__.py").exists()
    assert (root / "README.md").exists()


# ── تسجيل OCR في registry الأدوات ────────────────────────────────────────────

def _registry():
    from core.tools.registry import ToolRegistry
    return ToolRegistry(work_dir=".")


def test_ocr_tool_registered():
    r = _registry()
    assert "OCR" in r.names()
    assert "SymbolIndex" in r.names()
    # OCR يحتاج إذناً (يُشغّل عمليات + شبكة)
    assert r.requires_permission("OCR") is True
    # schema سليم
    sch = [t for t in r.get_schema() if t["function"]["name"] == "OCR"][0]
    props = sch["function"]["parameters"]["properties"]
    assert {"file_path", "tool", "server_url", "method", "detect_only"} <= set(props)


def test_ocr_tool_detect_only():
    import asyncio
    r = _registry()
    out = asyncio.run(r.execute("OCR", {"file_path": "/x/a.pdf", "detect_only": True}))
    assert "olmocr" in out
    out2 = asyncio.run(r.execute("OCR", {"file_path": "/x/a.png", "detect_only": True}))
    assert "chandra" in out2


def test_ocr_tool_unsupported():
    import asyncio
    r = _registry()
    out = asyncio.run(r.execute("OCR", {"file_path": "/x/a.txt"}))
    assert "غير مدعوم" in out


def test_ocr_tool_missing_file_is_graceful():
    import asyncio
    r = _registry()
    # ملف غير موجود → رسالة خطأ واضحة، لا استثناء
    out = asyncio.run(r.execute("OCR", {"file_path": "/nope/a.pdf",
                                        "server_url": "http://localhost:8000/v1"}))
    assert out.startswith("❌")
