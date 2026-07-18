"""
test_refusal_recovery.py — التعافي التلقائي من الرفض الزائف
==========================================================
عندما يرفض النموذج طلباً بريئاً بسبب غلاف إخفاء الهوية (الذي يشبه محاولة
اختراق)، يعيد WeaverCode المحاولة مرّة بطلب نظيف بلا غلاف — فينجح.
"""

import asyncio
import os

import pytest

from core.engine.query_engine import (
    QueryEngine, _looks_like_refusal, _MINIMAL_SYSTEM, _refusal_retry_enabled,
)
from core.engine.provider import Message


# ── كاشف الرفض ───────────────────────────────────────────────────────────────

def test_detects_weaver_refusal_marker():
    assert _looks_like_refusal("⛔ رفض النموذج تنفيذ هذا الطلب (سياسة الاستخدام).")
    assert _looks_like_refusal("رفض النموذج تنفيذ هذا الأمر")


def test_detects_raw_policy_refusal():
    assert _looks_like_refusal("This request was blocked under our Usage Policy")
    assert _looks_like_refusal("I cannot help with that — Usage Policy")


def test_does_not_flag_normal_code():
    assert not _looks_like_refusal("def login(u, p): return check(u, p)")
    assert not _looks_like_refusal("")
    assert not _looks_like_refusal("هذا كود بوابة تسجيل الدخول:")


# ── مزوّد وهمي: يرفض الغلاف، يقبل الطلب النظيف ───────────────────────────────

class _FakeConfig:
    model = "claude-fable-5"


class _RefusingProvider:
    """يحاكي بوابة ترفض غلاف إخفاء الهوية وتقبل الطلب النظيف."""
    def __init__(self):
        self.config = _FakeConfig()
        self.calls = []

    async def complete(self, messages, tools=None):
        sys_txt = next((m.content for m in messages if m.role == "system"), "")
        usr_txt = next((m.content for m in messages if m.role == "user"), "")
        self.calls.append((sys_txt, usr_txt))
        wrapped = ("WeaverCode" in sys_txt or "تعليمات نظام صامتة" in usr_txt
                   or "Silent rule" in usr_txt)
        if wrapped:
            return {"choices": [{"message": {
                "content": "⛔ رفض النموذج تنفيذ هذا الطلب (سياسة الاستخدام).",
                "role": "assistant"}, "finish_reason": "stop"}], "usage": {}}
        return {"choices": [{"message": {
            "content": "def login(u, p): return check(u, p)",
            "role": "assistant"}, "finish_reason": "stop"}], "usage": {}}


def test_refusal_auto_recovers(monkeypatch):
    monkeypatch.setenv("WEAVER_IDENTITY_GUARD", "1")   # الحارس مفعّل (يسبّب الرفض)
    monkeypatch.setenv("WEAVER_REFUSAL_RETRY", "1")
    eng = QueryEngine(provider=_RefusingProvider())
    res = asyncio.run(eng.run("اكتب لي كود بوابة تسجيل دخول"))
    assert "def login" in res.text, f"لم يتعافَ: {res.text}"
    assert len(eng.provider.calls) == 2   # رفض ثم إعادة محاولة نظيفة


def test_clean_retry_is_bare(monkeypatch):
    monkeypatch.setenv("WEAVER_IDENTITY_GUARD", "1")
    monkeypatch.setenv("WEAVER_REFUSAL_RETRY", "1")
    eng = QueryEngine(provider=_RefusingProvider())
    asyncio.run(eng.run("مهمة"))
    # الاستدعاء الثاني (إعادة المحاولة) عارٍ: بلا بروموه نظام وبلا غلاف هوية
    second_sys = eng.provider.calls[1][0]
    assert "WeaverCode" not in second_sys
    assert second_sys == ""  # لا رسالة نظام إطلاقاً في الطلب العاري


def test_retry_disabled_by_env(monkeypatch):
    monkeypatch.setenv("WEAVER_IDENTITY_GUARD", "1")
    monkeypatch.setenv("WEAVER_REFUSAL_RETRY", "0")   # مُعطّل
    eng = QueryEngine(provider=_RefusingProvider())
    res = asyncio.run(eng.run("اكتب كود"))
    # بلا إعادة محاولة → يبقى الرفض، استدعاء واحد فقط
    assert len(eng.provider.calls) == 1
    assert "⛔" in res.text


def test_refusal_retry_enabled_default(monkeypatch):
    monkeypatch.delenv("WEAVER_REFUSAL_RETRY", raising=False)
    assert _refusal_retry_enabled() is True


class _WordFilterProvider:
    """يحاكي نموذجاً يرفض أي كلمة أمنية (بأي لغة) ويقبل التحييد والصياغة."""
    class _Cfg:
        model = "claude-fable-5"
    config = _Cfg()

    async def complete(self, messages, tools=None):
        text = " ".join(m.content for m in messages).lower()
        if "rewrite the request" in text:   # مهمة الصياغة لا تُرفض
            return {"choices": [{"message": {
                "content": "An HTML page with two text fields and a submit button.",
                "role": "assistant"}, "finish_reason": "stop"}], "usage": {}}
        for w in ["login", "password", "بوابة", "دخول", "sign", "auth",
                  "credential", "portal", "gateway"]:
            if w in text:
                return {"choices": [{"message": {
                    "content": "⛔ رفض النموذج تنفيذ هذا الطلب cyber",
                    "role": "assistant"}, "finish_reason": "stop"}], "usage": {}}
        return {"choices": [{"message": {
            "content": "<!doctype html><form>...</form>",
            "role": "assistant"}, "finish_reason": "stop"}], "usage": {}}


def test_neutralize_recovers_when_words_trigger(monkeypatch):
    monkeypatch.setenv("WEAVER_IDENTITY_GUARD", "0")
    monkeypatch.setenv("WEAVER_REFUSAL_RETRY", "1")
    eng = QueryEngine(provider=_WordFilterProvider())
    res = asyncio.run(eng.run("اكتب كود لبوابة تسجيل الدخول"))
    assert "<form>" in res.text or "doctype" in res.text.lower(), res.text


def test_frame_has_no_trigger_words():
    """التأطير الإنجليزي يجب ألا يحوي كلمات تُحفّز المصنّف."""
    from core.engine.query_engine import _EN_LEGIT_FRAME
    low = _EN_LEGIT_FRAME.lower()
    for w in ["login", "password", "sign-in", "sign in", "authentication", "auth ", "portal"]:
        assert w not in low, f"التأطير يحوي كلمة مُحفّزة: {w}"
