"""
test_narration.py — نصّ المساعد المُتخلِّل بين الأدوات (كواجهة Claude Code)
=========================================================================
يتحقّق أنّ callback `on_narration` يُستدعى بشرح الجولات الوسيطة (التي تستدعي
أدوات) فقط، بينما يبقى النصّ النهائي (بلا أدوات) في result.text ولا يُبَثّ
كـ narration — فلا ازدواج بين «التفكير بصوت مسموع» والردّ النهائي.
"""

import asyncio
import json

from core.engine.query_engine import QueryEngine


class _Cfg:
    model = "test-model"


class _TwoRoundProvider:
    """جولة أولى: شرح + أداة. جولة ثانية: النصّ النهائي بلا أدوات."""

    def __init__(self):
        self.config = _Cfg()
        self.calls = 0

    async def complete(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return {"choices": [{"message": {
                "content": "الآن سأتحقّق من الملف.",
                "tool_calls": [{
                    "id": "t1",
                    "function": {"name": "Bash",
                                 "arguments": json.dumps({"command": "echo hi"})},
                }]}}]}
        return {"choices": [{"message": {
            "content": "اكتمل — كل شيء يعمل. هذا هو الجواب النهائي.",
            "role": "assistant"}}]}

    async def close(self):
        pass


def test_narration_intermediate_only(monkeypatch):
    monkeypatch.setenv("WEAVER_AUTO_APPROVE", "1")
    monkeypatch.setenv("WEAVER_LOOP_LIMIT", "0")
    monkeypatch.setenv("WEAVER_TASK_BUDGET", "0")
    narrated = []
    eng = QueryEngine(provider=_TwoRoundProvider())
    res = asyncio.run(eng.run("افحص الملف",
                              on_narration=lambda t: narrated.append(t)))
    # الشرح الوسيط بُثّ مرّة واحدة، والنصّ النهائي بقي result.text (لا يُبَثّ)
    assert narrated == ["الآن سأتحقّق من الملف."], narrated
    assert "الجواب النهائي" in res.text
    assert "الجواب النهائي" not in "".join(narrated)


def test_narration_optional_absent_when_no_prose(monkeypatch):
    """جولة أدوات بلا نصّ → لا narration (لا ضجيج)، والسلوك يبقى عاملاً."""
    monkeypatch.setenv("WEAVER_AUTO_APPROVE", "1")
    monkeypatch.setenv("WEAVER_LOOP_LIMIT", "0")
    monkeypatch.setenv("WEAVER_TASK_BUDGET", "0")

    class _SilentThenAnswer:
        def __init__(self):
            self.config = _Cfg()
            self.calls = 0

        async def complete(self, messages, tools=None):
            self.calls += 1
            if self.calls == 1:
                return {"choices": [{"message": {
                    "content": "",   # بلا شرح
                    "tool_calls": [{
                        "id": "t1",
                        "function": {"name": "Bash",
                                     "arguments": json.dumps({"command": "echo hi"})},
                    }]}}]}
            return {"choices": [{"message": {"content": "تم.", "role": "assistant"}}]}

        async def close(self):
            pass

    narrated = []
    eng = QueryEngine(provider=_SilentThenAnswer())
    res = asyncio.run(eng.run("نفّذ", on_narration=lambda t: narrated.append(t)))
    assert narrated == []
    assert res.text.strip() == "تم."
