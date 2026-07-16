"""اختبارات الميزات المتقدمة: الأدوات، أوامر السلاش، hooks، الوكلاء، البثّ."""

import os
import json
import asyncio
from pathlib import Path

from core.tools.registry import ToolRegistry
from core.commands import SlashCommands
from core.hooks import HookManager
from core.engine.query_engine import QueryEngine, Message
from core.memory.store import MemoryStore


# ── الأدوات ────────────────────────────────────────────────────────────────

def test_registry_has_new_tools():
    r = ToolRegistry()
    names = r.names()
    assert "MultiEdit" in names and "Agent" in names
    assert len(names) >= 27


def test_register_dynamic():
    r = ToolRegistry()
    r.register_dynamic("mcp__x__y", "d", {"type": "object", "properties": {}},
                       lambda **k: "ok", True)
    assert "mcp__x__y" in r.names()
    assert r.requires_permission("mcp__x__y") is True


def test_multi_edit(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("alpha beta gamma")
    r = ToolRegistry()
    out = asyncio.run(r.execute("MultiEdit", {"path": str(f), "edits": [
        {"old_string": "alpha", "new_string": "A"},
        {"old_string": "gamma", "new_string": "G"}]}))
    assert "✅" in out
    assert f.read_text() == "A beta G"


def test_multi_edit_atomic_on_failure(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("alpha")
    r = ToolRegistry()
    out = asyncio.run(r.execute("MultiEdit", {"path": str(f), "edits": [
        {"old_string": "alpha", "new_string": "A"},
        {"old_string": "NOPE", "new_string": "X"}]}))
    assert "فشل" in out
    assert f.read_text() == "alpha"  # لم يُحفظ أي تغيير


# ── أوامر السلاش ────────────────────────────────────────────────────────────

def test_slash_commands_load_and_parse():
    sc = SlashCommands()
    assert len(sc.names()) >= 1
    # أمر معروف
    known = sc.names()[0]
    parsed = sc.parse(f"/{known} arg1 arg2")
    assert parsed == (known, "arg1 arg2")
    # أمر غير معروف
    assert sc.parse("/definitely_not_a_command") is None


def test_slash_frontmatter_and_arguments(tmp_path):
    d = tmp_path / "commands"
    d.mkdir()
    (d / "hello.md").write_text("---\nname: hello\n---\nقل مرحباً لـ $ARGUMENTS")
    sc = SlashCommands(commands_dir=d)
    assert sc.render("hello", "بشار") == "قل مرحباً لـ بشار"


# ── Hooks ───────────────────────────────────────────────────────────────────

def test_hooks_matcher_and_deny(tmp_path):
    cfg = tmp_path / "hooks.json"
    cfg.write_text(json.dumps({"PreToolUse": [{"matcher": "Bash", "command": "exit 1"}]}))
    hm = HookManager(config_path=cfg)
    assert hm.has_any() is True
    # Bash يطابق → رمز خروج 1 → منع (False)
    assert hm.run("PreToolUse", "Bash", {}) is False
    # أداة أخرى لا تطابق → مسموح (True)
    assert hm.run("PreToolUse", "Read", {}) is True


def test_hooks_none_when_empty():
    # load_plugins=False لعزل الاختبار عن hooks الإضافات (plugins)
    hm = HookManager(config_path=Path("/nonexistent/hooks.json"),
                     load_plugins=False)
    assert hm.has_any() is False
    assert hm.run("PreToolUse", "Bash", {}) is True


# ── وكلاء فرعيون + بثّ ─────────────────────────────────────────────────────

class _SubMock:
    def __init__(self):
        self.n = 0

    async def complete(self, messages, tools=None):
        self.n += 1
        last_user = [m for m in messages if m.role == "user"][-1].content
        if "SUBTASK" in last_user:
            return {"choices": [{"message": {"role": "assistant",
                    "content": "نتيجة فرعية"}, "finish_reason": "stop"}]}
        if self.n == 1:
            return {"choices": [{"message": {"role": "assistant", "content": "",
                    "tool_calls": [{"id": "a1", "type": "function", "function": {
                        "name": "Agent",
                        "arguments": json.dumps({"prompt": "SUBTASK", "mode": "analysis"})}}]},
                    "finish_reason": "tool_calls"}]}
        return {"choices": [{"message": {"role": "assistant", "content": "خلاصة"},
                "finish_reason": "stop"}]}


def test_subagent_runs(monkeypatch):
    monkeypatch.setenv("WEAVER_AUTO_APPROVE", "1")
    eng = QueryEngine(provider=_SubMock(), tool_registry=ToolRegistry(),
                      memory=MemoryStore(), system_prompt="x")
    res = asyncio.run(eng.run("استخدم وكيلاً"))
    assert "Agent" in res.tool_calls_made
    assert res.text.strip() == "خلاصة"


class _StreamMock:
    """يحاكي stream_events: أول دور استدعاء أداة، ثم نصّ نهائي مبثوث."""
    def __init__(self):
        self.n = 0

    async def stream_events(self, messages, tools=None):
        self.n += 1
        if self.n == 1:
            yield {"type": "tool_calls", "tool_calls": [{"id": "s1", "type": "function",
                   "function": {"name": "Glob", "arguments": json.dumps({"pattern": "*.py"})}}]}
            yield {"type": "done", "finish_reason": "tool_calls"}
            return
        for tok in ["تمّت", " القراءة"]:
            yield {"type": "text", "text": tok}
        yield {"type": "done", "finish_reason": "stop"}


def test_streaming_runs_tools():
    eng = QueryEngine(provider=_StreamMock(), tool_registry=ToolRegistry(),
                      memory=MemoryStore(), system_prompt="x")

    async def collect():
        out, tools = "", []
        async for ch in eng.stream_run("اقرأ", on_tool=lambda n, a: tools.append(n)):
            out += ch
        return out, tools

    out, tools = asyncio.run(collect())
    assert "Glob" in tools
    assert "تمّت القراءة" in out
