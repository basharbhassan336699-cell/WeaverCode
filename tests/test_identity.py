"""اختبارات الهوية: المنقّي وحارس رسالة المستخدم وبروموه الهوية."""

import importlib
import core.engine.query_engine as qe
from prompts.system import get_system_prompt


def _reload_with(monkeypatch, mode):
    monkeypatch.setenv("WEAVER_IDENTITY_SANITIZE", mode)
    importlib.reload(qe)
    return qe


def test_sanitize_full_removes_all_brands(monkeypatch):
    m = _reload_with(monkeypatch, "full")
    s = "I'm Claude Code, Anthropic's CLI for Claude — powered by Claude Fable 5."
    out = m._sanitize_identity(s)
    for bad in ["Claude", "Anthropic", "Fable"]:
        assert bad not in out
    assert "WeaverCode" in out


def test_sanitize_arabic(monkeypatch):
    m = _reload_with(monkeypatch, "full")
    out = m._sanitize_identity("أنا كلود من أنثروبيك.")
    assert "كلود" not in out and "أنثروبيك" not in out
    assert "WeaverCode" in out


def test_sanitize_off(monkeypatch):
    m = _reload_with(monkeypatch, "off")
    s = "I am Claude Code."
    assert m._sanitize_identity(s) == s
    # أعد الوضع الافتراضي
    _reload_with(monkeypatch, "full")


def test_guard_appends_identity(monkeypatch):
    m = _reload_with(monkeypatch, "full")
    monkeypatch.setenv("WEAVER_IDENTITY_GUARD", "1")
    g = m._guard_user_prompt("من أنت؟")
    assert "WeaverCode" in g and "Claude" in g  # التذكير يذكر ألا يقول Claude
    monkeypatch.setenv("WEAVER_IDENTITY_GUARD", "0")
    assert m._guard_user_prompt("hi") == "hi"
    monkeypatch.setenv("WEAVER_IDENTITY_GUARD", "1")


def test_all_modes_enforce_identity():
    for mode in ["main", "coding", "project", "security", "autonomous", "analysis"]:
        s = get_system_prompt(mode)
        assert "WeaverCode" in s
        assert "أنا WeaverCode" in s
        assert "no preamble" in s  # قاعدة عدم التعريف التلقائي
