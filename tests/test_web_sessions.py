"""
test_web_sessions.py — اختبارات إصلاح عيب تسجيل المحادثات + الويب
=================================================================
العيب: كل رسالة داخل المحادثة كانت تُسجَّل كمحادثة منفصلة في القائمة الخارجية.
الإصلاح: محادثة واحدة = جلسة واحدة (session_id ثابت) تتراكم فيها الرسائل.
"""

import json
import os
import tempfile

import pytest


@pytest.fixture()
def mem(monkeypatch):
    """MemoryStore على قاعدة بيانات مؤقتة معزولة."""
    db = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("WEAVER_DB_PATH", db)
    from core.memory.store import MemoryStore
    return MemoryStore()


# ── العيب الأساسي: محادثة واحدة = عنصر واحد ──────────────────────────────────

def test_multi_turn_is_one_session(mem):
    sid = "s_1"
    msgs = [{"role": "user", "content": "س1"}, {"role": "assistant", "content": "ج1"}]
    mem.save_session(sid, "س1", "س1", json.dumps(msgs, ensure_ascii=False))
    msgs += [{"role": "user", "content": "س2"}, {"role": "assistant", "content": "ج2"}]
    mem.save_session(sid, "س1", "س2", json.dumps(msgs, ensure_ascii=False))
    msgs += [{"role": "user", "content": "س3"}, {"role": "assistant", "content": "ج3"}]
    mem.save_session(sid, "س1", "س3", json.dumps(msgs, ensure_ascii=False))

    sessions = mem.list_sessions()
    assert len(sessions) == 1, "يجب أن تكون محادثة واحدة لا ثلاث"
    loaded = mem.load_session(sid)
    assert len(loaded["messages"]) == 6


def test_two_separate_sessions(mem):
    mem.save_session("a", "أ", "أ", json.dumps([{"role": "user", "content": "x"}]))
    mem.save_session("b", "ب", "ب", json.dumps([{"role": "user", "content": "y"}]))
    assert len(mem.list_sessions()) == 2


def test_delete_session(mem):
    mem.save_session("d", "د", "د", json.dumps([{"role": "user", "content": "z"}]))
    assert len(mem.list_sessions()) == 1
    assert mem.delete_session("d") is True
    assert len(mem.list_sessions()) == 0


# ── طابور المهام يحمل session_id ─────────────────────────────────────────────

def test_queue_task_carries_session_id(monkeypatch, tmp_path):
    monkeypatch.setattr("background.status.QUEUE_FILE", tmp_path / "q.json")
    from background import status as st
    st.queue_task("مهمة", "main", [], "sess_xyz")
    tasks = st.read_queue()
    assert tasks[-1]["session_id"] == "sess_xyz"


# ── دوال الويب (بدون خادم) ───────────────────────────────────────────────────

def test_api_sessions_shape(mem):
    mem.save_session("w1", "عنوان", "آخر",
                     json.dumps([{"role": "user", "content": "a"},
                                 {"role": "assistant", "content": "b"}],
                                ensure_ascii=False))
    from web import server
    out = server._api_sessions()
    assert "sessions" in out
    ids = [s["id"] for s in out["sessions"]]
    assert "w1" in ids
    s = next(s for s in out["sessions"] if s["id"] == "w1")
    assert s["prompt"] == "عنوان"
    assert "timestamp" in s


def test_api_session_load_and_delete(mem):
    mem.save_session("w2", "ع", "آخر",
                     json.dumps([{"role": "user", "content": "1"},
                                 {"role": "assistant", "content": "2"}],
                                ensure_ascii=False))
    from web import server
    loaded = server._api_session("w2")
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0]["content"] == "1"
    # delete
    res = server._api_session_delete("w2")
    assert res["deleted"] is True
    assert server._api_session("w2")["messages"] == []


def test_api_sessions_search(mem):
    mem.save_session("s_a", "برمجة بايثون", "x", json.dumps([]))
    mem.save_session("s_b", "تصميم واجهة", "y", json.dumps([]))
    from web import server
    out = server._api_sessions(search="بايثون")
    ids = [s["id"] for s in out["sessions"]]
    assert "s_a" in ids and "s_b" not in ids


# ── WebFetch يعمل عبر curl (اتصال المواقع على Termux) ────────────────────────

def test_webfetch_has_curl_fallback():
    """يتأكد أن _http_get لا يعتمد على httpx حصراً (fallback إلى curl)."""
    import inspect
    from core.tools.registry import ToolRegistry
    src = inspect.getsource(ToolRegistry._http_get)
    assert "curl" in src
    assert "httpx" in src
    # _web_fetch يستدعي _http_get لا httpx مباشرة
    fetch_src = inspect.getsource(ToolRegistry._web_fetch)
    assert "_http_get" in fetch_src
