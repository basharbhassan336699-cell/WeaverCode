"""
اختبارات الميزات الأربع: وضع التخطيط (pending_plan + approve)، تتبع التعديلات
(+N -N)، محلّل الأوامر commands.parse، ونقاط لوحة الويب (plan/operations).
"""

import json
import os
import pathlib
import tempfile

import pytest


@pytest.fixture
def weaver_home(monkeypatch, tmp_path):
    """عزل ملفات ~/.weaver في مجلد مؤقت."""
    monkeypatch.setenv("WEAVER_DB_PATH", str(tmp_path / "memory.db"))
    return tmp_path


# ── الميزة ١: وضع التخطيط ────────────────────────────────────────────────────

def test_pending_plan_roundtrip(weaver_home):
    from core.engine.query_engine import (save_pending_plan, load_pending_plan,
                                          clear_pending_plan)
    save_pending_plan("١. أنشئ الملف\n٢. اختبر")
    assert "أنشئ الملف" in load_pending_plan()
    clear_pending_plan()
    assert load_pending_plan() == ""


def test_engine_has_plan_attrs(weaver_home):
    from core.engine.query_engine import QueryEngine
    from core.tools.registry import ToolRegistry

    class _P:  # مزوّد وهمي — لا اتصال
        class config:
            model = "m"
    e = QueryEngine.__new__(QueryEngine)
    # نتحقق من التهيئة عبر init الحقيقي بحقن مزوّد وهمي
    import core.engine.query_engine as qe
    e = object.__new__(qe.QueryEngine)
    e.__init__(provider=_P(), tool_registry=ToolRegistry(work_dir="/tmp"))
    assert e.pending_plan == ""
    assert isinstance(e.plan_mode, bool)


def test_plan_mode_env_activation(weaver_home, monkeypatch):
    monkeypatch.setenv("WEAVER_PLAN_MODE", "1")
    from core.engine.query_engine import QueryEngine
    from core.tools.registry import ToolRegistry

    class _P:
        class config:
            model = "m"
    import core.engine.query_engine as qe
    e = object.__new__(qe.QueryEngine)
    e.__init__(provider=_P(), tool_registry=ToolRegistry(work_dir="/tmp"))
    assert e.plan_mode is True


# ── الميزة ٢: تتبع التعديلات ─────────────────────────────────────────────────

def test_write_reports_diff_stats(weaver_home, tmp_path):
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir=str(tmp_path))
    out = reg._write("a.py", "x=1\ny=2\n")
    assert "+2" in out and "Created" in out


def test_edit_reports_diff_stats(weaver_home, tmp_path):
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir=str(tmp_path))
    reg._write("a.py", "x=1\ny=2\n")
    out = reg._edit("a.py", "y=2", "y=3\nz=4")
    assert "Edited" in out and "+2" in out and "-1" in out


def test_operations_log_retrievable(weaver_home, tmp_path):
    from core.tools.registry import ToolRegistry
    from core.oplog import read_operations, stat_label
    reg = ToolRegistry(work_dir=str(tmp_path))
    reg._write("f.py", "a\n")
    reg._edit("f.py", "a", "b")
    ops = read_operations()
    assert len(ops) >= 2
    assert ops[0]["action"] == "edited"  # الأحدث أولاً
    assert "+1 -1" in stat_label(ops[0])


def test_multi_edit_logs_once(weaver_home, tmp_path):
    from core.tools.registry import ToolRegistry
    from core.oplog import read_operations, clear_operations
    clear_operations()
    reg = ToolRegistry(work_dir=str(tmp_path))
    reg._write("m.py", "a=1\nb=2\n")
    clear_operations()
    reg._multi_edit("m.py", [{"old_string": "a=1", "new_string": "a=9"},
                             {"old_string": "b=2", "new_string": "b=8"}])
    ops = read_operations()
    assert len(ops) == 1 and ops[0]["added"] == 2


# ── الميزة ٤: محلّل الأوامر ──────────────────────────────────────────────────

def test_parse_known_commands():
    from core.commands import parse
    assert parse("/plan")["action"] == "plan_on"
    assert parse("/plan on")["action"] == "plan_on"
    assert parse("/plan off")["action"] == "plan_off"
    assert parse("/plan status")["action"] == "plan_status"
    assert parse("/approve")["action"] == "approve"
    assert parse("/execute")["action"] == "approve"


def test_parse_returns_arabic_confirmation():
    from core.commands import parse
    assert "التخطيط" in parse("/plan on")["message"]
    assert "تنفيذ" in parse("/approve")["message"]


def test_parse_unknown_returns_none():
    from core.commands import parse
    assert parse("مرحبا") is None
    assert parse("/weaver-status") is None
    assert parse("") is None


# ── الميزة ٥: نقاط لوحة الويب ────────────────────────────────────────────────

def _srv(tmp_path, monkeypatch):
    from web import server
    import background.status as st
    monkeypatch.setattr(server, "WEAVER_ROOT", tmp_path)
    (tmp_path / "config").mkdir(exist_ok=True)
    monkeypatch.setattr(st, "QUEUE_FILE", tmp_path / "q.json")
    monkeypatch.setattr(server.st, "QUEUE_FILE", tmp_path / "q.json")
    return server


def test_api_plan_toggle_and_get(weaver_home, tmp_path, monkeypatch):
    server = _srv(tmp_path, monkeypatch)
    monkeypatch.delenv("WEAVER_PLAN_MODE", raising=False)
    r = server._api_plan_toggle({"on": True})
    assert r["plan_mode"] is True and "التخطيط" in r["message"]
    assert server._api_plan_get()["plan_mode"] is True
    server._api_plan_toggle({"on": False})
    assert server._api_plan_get()["plan_mode"] is False


def test_api_plan_approve_queues_task(weaver_home, tmp_path, monkeypatch):
    server = _srv(tmp_path, monkeypatch)
    from core.engine.query_engine import save_pending_plan, load_pending_plan
    save_pending_plan("خطوة واحدة")
    r = server._api_plan_approve()
    assert r["ok"] is True and r["queued"] is True
    assert load_pending_plan() == ""          # فُرّغت
    assert server._api_plan_get()["plan_mode"] is False


def test_api_plan_approve_without_plan(weaver_home, tmp_path, monkeypatch):
    server = _srv(tmp_path, monkeypatch)
    from core.engine.query_engine import clear_pending_plan
    clear_pending_plan()
    r = server._api_plan_approve()
    assert r["ok"] is False


def test_api_operations_returns_labels(weaver_home, tmp_path, monkeypatch):
    server = _srv(tmp_path, monkeypatch)
    from core.oplog import log_operation, clear_operations
    clear_operations()
    log_operation("/x/main.py", "edited", 3, 1)
    r = server._api_operations()
    assert r["count"] == 1
    assert r["operations"][0]["label"] == "Edited main.py  +3 -1"
