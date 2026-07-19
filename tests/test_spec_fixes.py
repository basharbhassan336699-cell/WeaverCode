"""
test_spec_fixes.py — اختبارات إصلاحات المطلوب (write location + permission + sanitizer)
"""

import asyncio
import os
import tempfile

import pytest

from core.tools.registry import ToolRegistry
from core.prompt_sanitizer import sanitize_prompt
from core.engine.query_engine import (
    QueryEngine, PERM_ALLOW_ONCE, _sanitize_prompt,
)
from core.engine.provider import Message


# ── مكان الحفظ: نسبي → work_dir لا CWD ───────────────────────────────────────

def test_write_relative_goes_to_workdir(tmp_path):
    r = ToolRegistry(work_dir=str(tmp_path))
    r._write("sub/page.html", "<html></html>")
    assert (tmp_path / "sub" / "page.html").is_file()


def test_write_absolute_stays_absolute(tmp_path):
    target = tmp_path / "abs.txt"
    r = ToolRegistry(work_dir="/some/other/dir")
    r._write(str(target), "x")
    assert target.is_file()


def test_created_files_tracked(tmp_path):
    r = ToolRegistry(work_dir=str(tmp_path))
    r._write("a.txt", "1")
    r._write("b.txt", "2")
    assert len(r._created_files) == 2
    assert str(tmp_path / "a.txt") in r._created_files


def test_read_and_write_agree_on_relative(tmp_path):
    r = ToolRegistry(work_dir=str(tmp_path))
    r._write("note.txt", "hello world")
    assert "hello world" in r._read("note.txt")


# ── الأذونات: موافقة واحدة تكفي للجلسة ───────────────────────────────────────

def test_single_approval_whitelists_for_session():
    class _P:
        class _Cfg:
            model = "m"
        config = _Cfg()

        async def complete(self, messages, tools=None):
            return {"choices": [{"message": {"content": "ok", "role": "assistant"},
                                 "finish_reason": "stop"}], "usage": {}}

    eng = QueryEngine(provider=_P())
    # يحاكي التدفّق: بعد موافقة allow_once تُضاف الأداة لقائمة السماح
    eng.session_allow.add("Write")   # كما يفعل الكود بعد y
    assert eng._tool_pre_approved("Write") is True
    assert eng._tool_pre_approved("Bash") is False


def test_perm_allow_once_constant_exists():
    assert PERM_ALLOW_ONCE == "allow_once"


# ── المنقّي مدمج في المحرّك ───────────────────────────────────────────────────

def test_sanitizer_module_works():
    assert "access page" in sanitize_prompt("login portal")
    assert "الدخول" in sanitize_prompt("تسجيل الدخول")


def test_engine_imports_sanitizer():
    # الدالة المدمجة في المحرّك تعمل (وليست no-op فاشلة)
    assert _sanitize_prompt("login portal") != "login portal"


def test_sanitizer_disabled_by_env(monkeypatch):
    monkeypatch.setenv("WEAVER_PROMPT_SANITIZE", "0")
    assert sanitize_prompt("login portal") == "login portal"
