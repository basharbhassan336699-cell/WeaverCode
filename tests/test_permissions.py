"""اختبارات نظام الصلاحيات: الفحص، القرارات، والتنفيذ الفعلي في الحلقة."""

import os
import json
import asyncio
from core.engine.query_engine import QueryEngine, Message
from core.tools.registry import ToolRegistry
from core.memory.store import MemoryStore


def test_registry_permission_flags():
    r = ToolRegistry()
    assert r.requires_permission("Bash") is True
    assert r.requires_permission("Write") is True
    assert r.requires_permission("Read") is False
    assert r.requires_permission("Glob") is False
    # أداة مجهولة تُعامَل كخطرة
    assert r.requires_permission("DoesNotExist") is True


def _engine():
    return QueryEngine(provider=object(), tool_registry=ToolRegistry(),
                       memory=MemoryStore(), system_prompt="x")


def test_pre_approval_and_session_allow():
    e = _engine()
    assert e._tool_pre_approved("Bash") is False
    e.session_allow.add("Bash")
    assert e._tool_pre_approved("Bash") is True


def test_request_permission_decisions():
    e = _engine()
    assert e._request_permission("Bash", {}, lambda n, a: "deny") == "deny"
    assert e._request_permission("Bash", {}, lambda n, a: "allow_always") == "allow_always"
    # لا callback → رفض آمن
    assert e._request_permission("Bash", {}, None) == "deny"


class _BashMock:
    def __init__(self, marker):
        self.n = 0
        self.marker = marker

    async def complete(self, messages, tools=None):
        self.n += 1
        if self.n == 1:
            return {"choices": [{"message": {"role": "assistant", "content": "",
                    "tool_calls": [{"id": "b1", "type": "function", "function": {
                        "name": "Bash",
                        "arguments": json.dumps({"command": f"touch {self.marker}"})}}]},
                    "finish_reason": "tool_calls"}]}
        return {"choices": [{"message": {"role": "assistant", "content": "تم"},
                "finish_reason": "stop"}]}


def _run_with(decision, tmp_path):
    marker = str(tmp_path / "PERM.txt")
    if os.path.exists(marker):
        os.remove(marker)
    eng = QueryEngine(provider=_BashMock(marker), tool_registry=ToolRegistry(),
                      memory=MemoryStore(), system_prompt="x")
    asyncio.run(eng.run("نفّذ", on_permission=lambda n, a: decision))
    return os.path.exists(marker)


def test_deny_blocks_execution(tmp_path):
    assert _run_with("deny", tmp_path) is False


def test_allow_executes(tmp_path):
    assert _run_with("allow_once", tmp_path) is True
