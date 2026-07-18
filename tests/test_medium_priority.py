"""
test_medium_priority.py — اختبارات الميزات الست متوسطة الأولوية
==============================================================
1) MCP resources & prompts
2) add-dir / multi-workspace
3) checkpoint & rewind
4) bash background + kill
5) /init command (بروموه التوليد)
6) nested CLAUDE.md loading
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path

import pytest

from core.tools.registry import ToolRegistry
from core.checkpoint import CheckpointManager, Checkpoint
from core.claude_md import discover, load_nested_context
from core.mcp import MCPManager, _extract_resource_text, _extract_prompt_text


# ── 1) MCP resources & prompts ──────────────────────────────────────────────

def test_extract_resource_text():
    assert _extract_resource_text(
        {"contents": [{"uri": "x", "text": "hello"}]}) == "hello"
    # blob → وصف
    out = _extract_resource_text({"contents": [{"blob": "AAAA", "mimeType": "image/png"}]})
    assert "image/png" in out
    assert _extract_resource_text(None) == ""


def test_extract_prompt_text():
    out = _extract_prompt_text(
        {"messages": [{"role": "user", "content": {"type": "text", "text": "do X"}}]})
    assert out == "[user] do X"
    # content as list of blocks
    out2 = _extract_prompt_text(
        {"messages": [{"role": "system",
                       "content": [{"type": "text", "text": "sys"}]}]})
    assert out2 == "[system] sys"


class _FakeSrv:
    name = "fs"
    resources = [{"uri": "file://a", "name": "A"}]
    prompts = [{"name": "greet", "description": "greeting"}]

    async def read_resource(self, uri):
        return "CONTENT " + uri

    async def get_prompt(self, name, arguments=None):
        return "[user] hi " + name


def test_manager_list_resources_prompts():
    mgr = MCPManager()
    mgr.servers["fs"] = _FakeSrv()
    res = mgr.list_resources()
    pr = mgr.list_prompts()
    assert res[0]["_server"] == "fs" and res[0]["uri"] == "file://a"
    assert pr[0]["_server"] == "fs" and pr[0]["name"] == "greet"


def test_manager_read_resource_and_prompt():
    mgr = MCPManager()
    mgr.servers["fs"] = _FakeSrv()
    assert asyncio.run(mgr.read_resource("file://a")) == "CONTENT file://a"
    assert asyncio.run(mgr.get_prompt("greet")) == "[user] hi greet"
    # مورد غير موجود
    missing = asyncio.run(mgr.read_resource("file://nope", server_name="none"))
    assert "خطأ" in missing or "لم يُعثر" in missing


def test_register_resource_tools():
    mgr = MCPManager()
    reg = ToolRegistry()
    mgr._register_resource_tools(reg, _FakeSrv())
    assert "mcp__fs__read_resource" in reg.names()
    assert "mcp__fs__get_prompt" in reg.names()


# ── 2) add-dir / multi-workspace ────────────────────────────────────────────

def test_add_dir_and_workspace_dirs(tmp_path):
    d2 = tmp_path / "extra"
    d2.mkdir()
    reg = ToolRegistry(work_dir=str(tmp_path))
    msg = reg.add_dir(str(d2))
    assert "✅" in msg
    dirs = reg.workspace_dirs()
    assert str(tmp_path.resolve()) in dirs
    assert str(d2.resolve()) in dirs
    # إضافة مكرّرة
    again = reg.add_dir(str(d2))
    assert "مسبقاً" in again
    # مجلد غير موجود
    bad = reg.add_dir(str(tmp_path / "nope"))
    assert "غير موجود" in bad


def test_multiworkspace_glob_and_grep(tmp_path):
    d1 = tmp_path / "a"
    d2 = tmp_path / "b"
    d1.mkdir()
    d2.mkdir()
    (d1 / "one.txt").write_text("needle here", encoding="utf-8")
    (d2 / "two.txt").write_text("needle there", encoding="utf-8")
    reg = ToolRegistry(work_dir=str(d1))
    reg.add_dir(str(d2))
    g = reg._glob("**/*.txt")
    assert "one.txt" in g and "two.txt" in g
    gr = reg._grep("needle", output_mode="files_with_matches")
    assert "one.txt" in gr and "two.txt" in gr


# ── 3) checkpoint & rewind ──────────────────────────────────────────────────

def test_checkpoint_rewind_edit(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("original", encoding="utf-8")
    cm = CheckpointManager()
    cm.snapshot("Edit", str(f))
    f.write_text("v1", encoding="utf-8")
    cp = cm.rewind()
    assert cp is not None
    assert f.read_text() == "original"


def test_checkpoint_rewind_new_file_deletes(tmp_path):
    nf = tmp_path / "new.txt"
    cm = CheckpointManager()
    cm.snapshot("Write", str(nf))
    nf.write_text("created", encoding="utf-8")
    assert nf.exists()
    cm.rewind()
    assert not nf.exists()


def test_checkpoint_rewind_to(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("base", encoding="utf-8")
    cm = CheckpointManager()
    cm.snapshot("Edit", str(f))
    f.write_text("x1", encoding="utf-8")
    cm.snapshot("Edit", str(f))
    f.write_text("x2", encoding="utf-8")
    restored = cm.rewind_to(1)
    assert len(restored) == 2
    assert f.read_text() == "base"
    assert cm.count() == 0


def test_checkpoint_is_write_tool():
    assert CheckpointManager.is_write_tool("Edit")
    assert CheckpointManager.is_write_tool("NotebookEdit")
    assert not CheckpointManager.is_write_tool("Bash")
    assert not CheckpointManager.is_write_tool("Read")


def test_checkpoint_empty_rewind():
    cm = CheckpointManager()
    assert cm.rewind() is None
    assert cm.rewind_to(5) == []


# ── 4) bash background + kill ────────────────────────────────────────────────

def test_bash_background_completes():
    reg = ToolRegistry()
    out = reg._bash("echo start; echo done", run_in_background=True)
    assert "bash_" in out
    sid = "bash_1"
    time.sleep(0.6)
    res = reg._bash_output(sid)
    assert "start" in res and "done" in res
    assert "انتهى" in res
    # تنظيف
    reg._kill_shell(sid)


def test_bash_kill_running():
    reg = ToolRegistry()
    out = reg._bash("sleep 30", run_in_background=True)
    # استخرج المعرّف
    sid = None
    for line in out.splitlines():
        if line.startswith("🚀"):
            sid = line.split(":")[1].strip()
    assert sid
    time.sleep(0.2)
    k = reg._kill_shell(sid)
    assert "أُنهي" in k
    # الآن غير موجود
    assert "لا يوجد" in reg._bash_output(sid)


def test_bash_output_unknown_shell():
    reg = ToolRegistry()
    assert "لا يوجد" in reg._bash_output("bash_999")
    assert "لا يوجد" in reg._kill_shell("bash_999")


def test_list_background_shells():
    reg = ToolRegistry()
    reg._bash("sleep 5", run_in_background=True)
    shells = reg.list_background_shells()
    assert len(shells) == 1
    assert shells[0]["running"] in (True, False)
    # cleanup
    for s in shells:
        reg._kill_shell(s["shell_id"])


# ── 5) /init command ────────────────────────────────────────────────────────

def test_init_prompt_constant():
    import weaver
    assert "CLAUDE.md" in weaver._INIT_PROMPT
    assert "Write" in weaver._INIT_PROMPT
    # موجود ضمن أوامر الإكمال المدمجة
    names = [c["name"] for c in weaver._BUILTIN_CMDS]
    assert "init" in names
    assert "rewind" in names
    assert "add-dir" in names


# ── 6) nested CLAUDE.md ──────────────────────────────────────────────────────

def _build_tree(root: Path):
    (root / "CLAUDE.md").write_text("# Root", encoding="utf-8")
    (root / "backend").mkdir()
    (root / "backend" / "CLAUDE.md").write_text("# Backend rules", encoding="utf-8")
    (root / "backend" / "api").mkdir()
    (root / "backend" / "api" / "CLAUDE.md").write_text("# API rules", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "CLAUDE.md").write_text("# skip me", encoding="utf-8")


def test_discover_nested(tmp_path):
    _build_tree(tmp_path)
    files = discover(str(tmp_path))
    rels = [str(f.relative_to(tmp_path)) for f in files
            if str(f).startswith(str(tmp_path))]
    assert "backend/CLAUDE.md" in rels
    assert "backend/api/CLAUDE.md" in rels
    assert not any("node_modules" in r for r in rels)


def test_load_nested_excludes_root(tmp_path):
    _build_tree(tmp_path)
    ctx = load_nested_context(str(tmp_path), root_md=str(tmp_path / "CLAUDE.md"))
    assert "Backend rules" in ctx
    assert "API rules" in ctx
    assert "# Root" not in ctx


def test_load_nested_empty(tmp_path):
    # لا ملفات CLAUDE.md فرعية
    (tmp_path / "CLAUDE.md").write_text("# only root", encoding="utf-8")
    ctx = load_nested_context(str(tmp_path), root_md=str(tmp_path / "CLAUDE.md"))
    assert ctx == ""
