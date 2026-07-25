"""
test_loop_guard.py — حارس ضدّ «يفكّر بلا رد»
=============================================
نموذج ضعيف مع أدوات كثيرة قد يدور على الأدوات كل الدورات (مثل «هلا» فيستدعي
Bash مراراً) فيبقى «يفكّر» دقائق دون ردّ مفيد. نتحقّق أنّ:

  1. كشف الدوران يوقف المهمة بعد تكرار نفس (الأداة+الوسائط) بردٍّ واضح.
  2. الميزانية الزمنية توقف المهمة عند تجاوز الحدّ بردٍّ واضح.
  3. تعطيل الحدّين (0) يُبقي السلوك القديم (حتى max_turns).
"""

import asyncio
import json

from core.engine.query_engine import QueryEngine, _looks_like_guard_verdict


class _FakeConfig:
    model = "test-model"


class _LoopProvider:
    """يعيد الاستدعاء ذاته دائماً — يحاكي نموذجاً ضعيفاً يدور على أداة واحدة."""

    def __init__(self, args=None):
        self.config = _FakeConfig()
        self.calls = 0
        self._args = args if args is not None else {"command": "echo hi"}

    async def complete(self, messages, tools=None):
        self.calls += 1
        return {"choices": [{"message": {
            "content": "",
            "tool_calls": [{
                "id": f"t{self.calls}",
                "function": {"name": "Bash",
                             "arguments": json.dumps(self._args)},
            }]}}]}

    async def close(self):
        pass


class _DistinctToolProvider:
    """يعيد أداة بوسائط مختلفة كل مرّة — لا يُطلقه كاشف الدوران، بل الميزانية."""

    def __init__(self):
        self.config = _FakeConfig()
        self.calls = 0

    async def complete(self, messages, tools=None):
        self.calls += 1
        return {"choices": [{"message": {
            "content": "",
            "tool_calls": [{
                "id": f"t{self.calls}",
                "function": {"name": "Bash",
                             "arguments": json.dumps({"command": f"echo {self.calls}"})},
            }]}}]}

    async def close(self):
        pass


def test_loop_guard_stops_repeated_tool(monkeypatch):
    """تكرار نفس الاستدعاء يتوقّف بعد الحدّ بدل استنزاف كل الدورات."""
    monkeypatch.setenv("WEAVER_MAX_TURNS", "20")
    monkeypatch.setenv("WEAVER_LOOP_LIMIT", "4")
    monkeypatch.setenv("WEAVER_TASK_BUDGET", "0")   # الميزانية معطّلة — نختبر الدوران فقط
    monkeypatch.setenv("WEAVER_AUTO_APPROVE", "1")
    eng = QueryEngine(provider=_LoopProvider())
    res = asyncio.run(eng.run("هلا"))
    assert res.looped is True
    # الحدّ 4 → يتوقّف عند الاستدعاء الخامس (لا 20)
    assert eng.provider.calls == 5, eng.provider.calls
    assert "كرّر النموذج الأداة نفسها" in res.text


def test_time_budget_stops_slow_task(monkeypatch):
    """تجاوز الميزانية الزمنية يوقف المهمة بردٍّ واضح بدل تعليق طويل."""
    monkeypatch.setenv("WEAVER_MAX_TURNS", "50")
    monkeypatch.setenv("WEAVER_TASK_BUDGET", "0.01")   # صغيرة جداً → تُطلق فوراً
    monkeypatch.setenv("WEAVER_LOOP_LIMIT", "0")       # الدوران معطّل — نختبر الميزانية فقط
    monkeypatch.setenv("WEAVER_AUTO_APPROVE", "1")
    eng = QueryEngine(provider=_DistinctToolProvider())
    res = asyncio.run(eng.run("نفّذ مهمة طويلة"))
    assert res.timed_out is True
    assert eng.provider.calls < 50            # توقّف قبل استنفاد الدورات
    assert "الحدّ الزمني" in res.text


class _GuardModelProvider:
    """يحاكي نموذج فحص أمان (NemoGuard) يردّ بحكم سلامة بدل الإجابة."""

    def __init__(self, verdict='{"User Safety": "safe", "Response Safety": "safe"}'):
        self.config = _FakeConfig()
        self._verdict = verdict

    async def complete(self, messages, tools=None):
        return {"choices": [{"message": {"content": self._verdict, "role": "assistant"}}]}

    async def close(self):
        pass


def test_detects_guard_verdict():
    assert _looks_like_guard_verdict('{"User Safety": "safe", "Response Safety": "safe"}')
    assert _looks_like_guard_verdict('{"Response Safety": "unsafe"}')
    assert _looks_like_guard_verdict("safe")
    assert _looks_like_guard_verdict("unsafe\nS1")
    # لا إيجابيات كاذبة: ردود دردشة عادية
    assert not _looks_like_guard_verdict("أهلاً! كيف أساعدك اليوم؟")
    assert not _looks_like_guard_verdict("الكود آمن ولا يحوي ثغرات — إليك الشرح المفصّل ...")
    assert not _looks_like_guard_verdict("")


def test_guard_model_gets_clear_hint(monkeypatch):
    """رد نموذج Guard يُستبدل برسالة إرشادية لاختيار نموذج دردشة."""
    monkeypatch.setenv("WEAVER_AUTO_APPROVE", "1")
    eng = QueryEngine(provider=_GuardModelProvider())
    res = asyncio.run(eng.run("هلا"))
    assert "فحص أمان" in res.text
    assert "User Safety" not in res.text or "بدل الإجابة" in res.text


def test_guards_disabled_runs_to_max_turns(monkeypatch):
    """تعطيل الحدّين (0) يُبقي السلوك القديم: يدور حتى max_turns."""
    monkeypatch.setenv("WEAVER_MAX_TURNS", "6")
    monkeypatch.setenv("WEAVER_LOOP_LIMIT", "0")
    monkeypatch.setenv("WEAVER_TASK_BUDGET", "0")
    monkeypatch.setenv("WEAVER_AUTO_APPROVE", "1")
    eng = QueryEngine(provider=_LoopProvider())
    res = asyncio.run(eng.run("هلا"))
    assert res.looped is False
    assert res.timed_out is False
    assert eng.provider.calls == 6            # دار حتى max_turns بلا حارس
