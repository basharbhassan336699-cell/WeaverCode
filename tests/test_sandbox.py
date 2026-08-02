"""
test_sandbox.py — بيئة التنفيذ المعزولة (proot) — اختيارية ومعطّلة افتراضياً
==========================================================================
يتحقّق أنّ الميزة:
- معطّلة افتراضياً فلا تغيّر سلوك Bash القائم،
- تتراجع بأمان (fallback) إن غاب proot،
- عند تفعيلها تُوجَّه أوامر Bash عبر run_sandboxed،
- أي عطل في الوحدة لا يكسر التنفيذ العادي.
"""

import asyncio
import tempfile

import pytest

from core import sandbox
from core.tools.registry import ToolRegistry


def test_defaults_off(monkeypatch):
    monkeypatch.delenv("WEAVER_SANDBOX", raising=False)
    assert sandbox.is_enabled() is False        # معطّل افتراضياً


def test_enabled_requires_proot(monkeypatch):
    monkeypatch.setenv("WEAVER_SANDBOX", "1")
    # يتطلّب proot فعلياً؛ في غيابه يبقى معطّلاً (لا يدّعي عزلاً غير موجود)
    assert sandbox.is_enabled() == sandbox.is_available()


def test_result_output_format():
    r = sandbox.SandboxResult("hi", "oops", 2, timed_out=True)
    o = r.output
    assert "hi" in o and "[STDERR]: oops" in o and "[EXIT]: 2" in o and "[TIMEOUT]" in o


def test_fallback_runs_without_proot(monkeypatch):
    """بلا proot: run_sandboxed يشغّل الأمر عادياً مع تحذير واضح (لا يفشل)."""
    monkeypatch.setattr(sandbox.shutil, "which", lambda _n: None)   # اجبر غياب proot
    r = asyncio.run(sandbox.run_sandboxed("echo hello123"))
    assert "hello123" in r.output
    assert "proot غير متاح" in r.output


def test_bash_unchanged_when_off(monkeypatch):
    monkeypatch.delenv("WEAVER_SANDBOX", raising=False)
    t = ToolRegistry(work_dir=tempfile.mkdtemp())
    out = t._bash("echo plain-run")
    assert "plain-run" in out
    assert "proot" not in out and "sandbox" not in out.lower()


def test_bash_routes_through_sandbox_when_on(monkeypatch):
    """عند التفعيل: يمرّ الأمر عبر الـ sandbox (يتراجع لتشغيل عادي بلا proot)."""
    monkeypatch.setattr(sandbox, "is_enabled", lambda: True)
    monkeypatch.setattr(sandbox.shutil, "which", lambda _n: None)   # لا proot → fallback
    t = ToolRegistry(work_dir=tempfile.mkdtemp())
    out = t._bash("echo routed-through-sandbox")
    assert "routed-through-sandbox" in out
    assert "proot غير متاح" in out          # دليل أنّه مرّ عبر run_sandboxed


def test_bash_survives_broken_sandbox(monkeypatch):
    """لو انكسرت وحدة الـ sandbox، لا يتعطّل Bash (لا ضرر)."""
    def _boom():
        raise RuntimeError("boom")
    monkeypatch.setattr(sandbox, "is_enabled", _boom)
    t = ToolRegistry(work_dir=tempfile.mkdtemp())
    out = t._bash("echo still-works")
    assert "still-works" in out


# ── التحقّق الذاتي داخل الـ sandbox (verify_python) ─────────────────────────────
def test_verify_python_pass(tmp_path):
    f = tmp_path / "good.py"; f.write_text("a = 1 + 1\n")
    ok, s = asyncio.run(sandbox.verify_python([str(f)], str(tmp_path)))
    assert ok is True and "تم التحقق" in s


def test_verify_python_fail(tmp_path):
    f = tmp_path / "bad.py"; f.write_text("def broken(:\n    pass\n")
    ok, s = asyncio.run(sandbox.verify_python([str(f)], str(tmp_path)))
    assert ok is False and "فشل التحقق" in s


def test_verify_python_ignores_non_python(tmp_path):
    ok, s = asyncio.run(sandbox.verify_python([str(tmp_path / "notes.txt")], str(tmp_path)))
    assert ok is True and s == ""


def test_written_py_files_extraction():
    from background.daemon import WeaverDaemon
    from core.action_blocks import ActionBlock, ToolOp

    class _R:
        pass
    r = _R()
    r.blocks = [ActionBlock(ops=[
        ToolOp(tool_name="Write", args={"path": "a.py"}, result="ok"),
        ToolOp(tool_name="Edit", args={"path": "b.py"}, result="ok"),
        ToolOp(tool_name="Write", args={"path": "notes.txt"}, result="ok"),
        ToolOp(tool_name="Bash", args={"command": "ls"}, result="ok"),
    ])]
    files = WeaverDaemon()._written_py_files(r)
    assert files == ["a.py", "b.py"]
