"""
اختبارات منع انفجار السياق: قراءة واحدة مقيّدة + حدّ تراكم نتائج الأدوات في الحلقة.
يعالج «الرد الفارغ من أول رسالة» بسبب قراءة ملف كبير يبتلع ميزانية النموذج.
"""

import os
import tempfile


def test_single_read_is_capped():
    from core.filetypes import read_any
    f = tempfile.mktemp(suffix=".txt")
    open(f, "w").write("x" * 500000)
    try:
        out = read_any(f)
        assert len(out) < 30000  # ~6k توكن بدل ~125k
        assert "اقتُطع" in out
    finally:
        os.unlink(f)


def test_read_cap_env_override(monkeypatch):
    monkeypatch.setenv("WEAVER_READ_MAX_CHARS", "5000")
    import importlib
    import core.filetypes as ft
    importlib.reload(ft)
    try:
        f = tempfile.mktemp(suffix=".txt")
        open(f, "w").write("y" * 100000)
        out = ft.read_any(f)
        assert len(out) < 8000
        os.unlink(f)
    finally:
        monkeypatch.delenv("WEAVER_READ_MAX_CHARS", raising=False)
        importlib.reload(ft)


def test_bound_context_trims_old_tool_results():
    from core.engine.provider import Message
    from core.engine.query_engine import _bound_context
    msgs = [Message(role="system", content="S")]
    for i in range(10):
        msgs.append(Message(role="tool", content="R" * 20000, tool_call_id=f"t{i}"))
    total_before = sum(len(m.content) for m in msgs)
    _bound_context(msgs, max_chars=60000, keep_recent=3)
    total_after = sum(len(m.content) for m in msgs)
    assert total_after < total_before
    assert total_after <= 80000
    # النظام + آخر 3 رسائل تبقى كاملة
    assert msgs[0].content == "S"
    assert all(len(m.content) == 20000 for m in msgs[-3:])


def test_bound_context_noop_when_small():
    from core.engine.provider import Message
    from core.engine.query_engine import _bound_context
    msgs = [Message(role="system", content="S"),
            Message(role="user", content="hi"),
            Message(role="assistant", content="ok")]
    _bound_context(msgs, max_chars=120000)
    assert msgs[1].content == "hi" and msgs[2].content == "ok"
