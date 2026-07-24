"""
اختبارات سجل العمليات الهرمي (3 مستويات كواجهة Claude Code):
- المستوى 1: صحة تجميع الملخّص المصغّر من العمليات.
- المستوى 2: قائمة عمليات الدفعة.
- المستوى 3: endpoint تفاصيل عملية واحدة + كفاية البيانات المخزّنة لإعادة البناء.
"""

import os

import pytest


@pytest.fixture
def openv(tmp_path, monkeypatch):
    monkeypatch.setenv("WEAVER_DB_PATH", str(tmp_path / "memory.db"))
    from core import oplog
    oplog.clear_operations()
    return oplog


# ── المستوى 1: الملخّص ───────────────────────────────────────────────────────

def test_summary_counts_by_type(openv):
    ops = ([{"type": "edit"}] * 3 + [{"type": "run"}] * 2 + [{"type": "read"}])
    s = openv.summarize_batch(ops)
    assert s == "Edited 3 files, ran 2 commands, read 1 file"


def test_summary_singular_plural(openv):
    assert openv.summarize_batch([{"type": "edit"}]) == "Edited 1 file"
    assert "created 2 files" in openv.summarize_batch(
        [{"type": "create"}, {"type": "create"}])


def test_summary_empty(openv):
    assert openv.summarize_batch([]) == "لا عمليات"


# ── التسجيل + الدفعات ────────────────────────────────────────────────────────

def test_batch_groups_operations(openv):
    openv.start_batch()
    openv.log_operation("a.py", "created", 2, 0, op_type="create", content="x")
    openv.log_operation("a.py", "edited", 1, 1, op_type="edit", before="x", after="y")
    openv.start_batch()  # دفعة ثانية
    openv.log_operation("", "run", op_type="run", command="ls", output="a.py")
    batches = openv.read_batches()
    assert len(batches) == 2
    # الأحدث أولاً → الدفعة الثانية (run) أولاً
    assert batches[0]["count"] == 1
    assert "ran 1 command" in batches[0]["summary"]
    assert batches[1]["count"] == 2


def test_op_line_has_display_fields(openv):
    openv.start_batch()
    openv.log_operation("main.py", "edited", 5, 2, op_type="edit",
                        before="a", after="b")
    b = openv.read_batches()[0]
    line = b["operations"][0]
    assert line["verb"] == "Edited" and line["icon"] == "✏️"
    assert line["added"] == 5 and line["removed"] == 2
    assert "id" in line


# ── المستوى 3: تفاصيل + كفاية البيانات ───────────────────────────────────────

def test_read_operation_by_id_edit(openv):
    openv.start_batch()
    e = openv.log_operation("f.py", "edited", 1, 1, op_type="edit",
                            before="old code", after="new code")
    o = openv.read_operation(e["id"])
    assert o is not None
    assert o["before"] == "old code" and o["after"] == "new code"  # كافٍ لإعادة بناء diff


def test_read_operation_run_has_command_and_output(openv):
    openv.start_batch()
    e = openv.log_operation("", "run", op_type="run",
                            command="echo hi", output="hi\n")
    o = openv.read_operation(e["id"])
    assert o["command"] == "echo hi" and o["output"] == "hi\n"


def test_read_operation_read_has_content(openv):
    openv.start_batch()
    e = openv.log_operation("r.txt", "read", op_type="read", content="line1\nline2")
    o = openv.read_operation(e["id"])
    assert o["content"] == "line1\nline2"


def test_read_operation_missing_returns_none(openv):
    assert openv.read_operation("nope") is None


def test_large_field_is_clipped(openv):
    openv.start_batch()
    e = openv.log_operation("big.py", "created", 1, 0, op_type="create",
                            content="x" * 50000)
    o = openv.read_operation(e["id"])
    assert len(o["content"]) < 30000 and "اقتُطع" in o["content"]


# ── الـ endpoints في الخادم ──────────────────────────────────────────────────

def _srv(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "WEAVER_ROOT", tmp_path)
    (tmp_path / "config").mkdir(exist_ok=True)
    return server


def test_api_operations_returns_batches(openv, tmp_path, monkeypatch):
    server = _srv(tmp_path, monkeypatch)
    openv.start_batch()
    openv.log_operation("a.py", "created", 2, 0, op_type="create", content="x")
    openv.log_operation("", "run", op_type="run", command="ls", output="a.py")
    r = server._api_operations()
    assert "batches" in r and r["batches"]
    b = r["batches"][0]
    assert b["count"] == 2 and "operations" in b
    assert "operations" in r  # توافق للخلف (قائمة مسطّحة)


def test_api_operation_detail_endpoint(openv, tmp_path, monkeypatch):
    server = _srv(tmp_path, monkeypatch)
    openv.start_batch()
    e = openv.log_operation("x.py", "edited", 1, 1, op_type="edit",
                            before="a", after="b")
    r = server._api_operation_detail(e["id"])
    assert r["ok"] is True
    assert r["operation"]["before"] == "a" and r["operation"]["after"] == "b"
    # معرّف خاطئ
    assert server._api_operation_detail("bad")["ok"] is False


# ── التكامل مع السجل (registry) ───────────────────────────────────────────────

def test_registry_tools_log_all_types(openv, tmp_path):
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir=str(tmp_path))
    openv.start_batch()
    reg._write("a.py", "x=1\n")
    reg._edit("a.py", "x=1", "x=2")
    reg._read(str(tmp_path / "a.py"))
    reg._bash("echo done")
    b = openv.read_batches()[0]
    types = {op["type"] for op in b["operations"]}
    assert types == {"create", "edit", "read", "run"}
    assert "read 1 file" in b["summary"] and "ran 1 command" in b["summary"]
