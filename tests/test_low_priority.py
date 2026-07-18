"""
test_low_priority.py — اختبارات ميزات الأولوية المنخفضة (تحسينات/تجميل)
=======================================================================
1) تتبّع التكلفة بالدولار + التوكنات (core/cost.py)
2) أوامر مدمجة: /cost /context /clear /compact /agents (منطقها في المحرّك)
3) وضع Vim (إعداد PromptSession)
4) امتداد VS Code (ملفات حقيقية صالحة)
"""

import asyncio
import json
from pathlib import Path

import pytest

from core.cost import (
    CostTracker, TokenUsage, resolve_price, estimate_tokens, _extract_tokens,
)
from core.engine.query_engine import QueryEngine
from core.engine.provider import Message


# ── 1) تتبّع التكلفة ─────────────────────────────────────────────────────────

def test_resolve_price_known_models():
    assert resolve_price("claude-opus-4-8")[0] == 15.0
    assert resolve_price("gpt-4o-mini") == (0.15, 0.60)
    assert resolve_price("deepseek-chat") == (0.27, 1.10)


def test_resolve_price_local_free():
    assert resolve_price("ollama/llama3") == (0.0, 0.0)
    assert resolve_price("http://localhost:11434") == (0.0, 0.0)


def test_resolve_price_unknown():
    assert resolve_price("totally-made-up-xyz") == (0.0, 0.0)


def test_resolve_price_env_override(monkeypatch):
    monkeypatch.setenv("WEAVER_PRICE_INPUT", "1.5")
    monkeypatch.setenv("WEAVER_PRICE_OUTPUT", "6.0")
    assert resolve_price("anything") == (1.5, 6.0)


def test_extract_tokens_both_shapes():
    assert _extract_tokens({"prompt_tokens": 100, "completion_tokens": 50}) == (100, 50)
    assert _extract_tokens({"input_tokens": 200, "output_tokens": 80}) == (200, 80)
    assert _extract_tokens({}) == (0, 0)
    assert _extract_tokens(None) == (0, 0)


def test_cost_tracker_accumulates():
    ct = CostTracker()
    i, o, c = ct.record({"usage": {"prompt_tokens": 1000, "completion_tokens": 500},
                         "model": "claude-opus-4-8"})
    assert (i, o) == (1000, 500)
    # 1000/1e6*15 + 500/1e6*75 = 0.0525
    assert abs(c - 0.0525) < 1e-9
    ct.record({"usage": {"prompt_tokens": 2000, "completion_tokens": 1000},
               "model": "claude-opus-4-8"})
    assert ct.usage.requests == 2
    assert ct.usage.input_tokens == 3000
    assert ct.usage.output_tokens == 1500
    assert ct.usage.total_tokens == 4500
    assert ct.usage.pricing_known is True


def test_cost_tracker_unknown_pricing_flag():
    ct = CostTracker()
    ct.record({"usage": {"prompt_tokens": 100, "completion_tokens": 50},
               "model": "unknown-model-zzz"})
    assert ct.usage.pricing_known is False
    assert "تقديرية" in ct.summary()


def test_cost_tracker_reset():
    ct = CostTracker()
    ct.record({"usage": {"prompt_tokens": 10, "completion_tokens": 5}, "model": "gpt-4o"})
    ct.reset()
    assert ct.usage.total_tokens == 0
    assert ct.usage.requests == 0


def test_cost_tracker_ignores_garbage():
    ct = CostTracker()
    assert ct.record("not a dict") == (0, 0, 0.0)
    assert ct.record({}) == (0, 0, 0.0)


def test_estimate_tokens():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") > 0
    # نص أطول → توكنات أكثر
    assert estimate_tokens("x" * 100) > estimate_tokens("x" * 10)


# ── 2) منطق الأوامر المدمجة في المحرّك ───────────────────────────────────────

def test_engine_has_cost_tracker():
    eng = QueryEngine()
    assert eng.cost is not None
    assert isinstance(eng.cost, CostTracker)


def test_engine_context_stats():
    eng = QueryEngine()
    hist = [Message(role="user", content="a" * 400),
            Message(role="assistant", content="b" * 800)]
    st = eng.context_stats(hist)
    assert st["messages"] == 2
    assert st["tokens"] > 0
    assert 0 <= st["percent"] <= 100
    assert st["window"] > 0


def test_engine_context_stats_empty():
    eng = QueryEngine()
    st = eng.context_stats([])
    assert st["messages"] == 0
    # ما زال يحسب توكنات البروموه النظامي
    assert st["tokens"] >= 0


def test_compact_history_short_noop():
    eng = QueryEngine()
    hist = [Message(role="user", content="hi"),
            Message(role="assistant", content="hello")]
    new_hist, msg = asyncio.run(eng.compact_history(hist))
    assert new_hist is hist
    assert "قصيرة" in msg


def test_compact_history_empty():
    eng = QueryEngine()
    new_hist, msg = asyncio.run(eng.compact_history([]))
    assert "قصيرة" in msg


# ── 3) وضع Vim + الأوامر المدمجة في القائمة ──────────────────────────────────

def test_builtin_commands_registered():
    import weaver
    names = [c["name"] for c in weaver._BUILTIN_CMDS]
    for expected in ("cost", "context", "clear", "compact", "agents", "vim"):
        assert expected in names, f"{expected} missing from builtin commands"


def test_list_agents_returns_dict():
    import weaver
    agents = weaver._list_agents()
    assert isinstance(agents, dict)
    # plugins تحوي وكلاء عادةً
    for name, (source, path) in agents.items():
        assert source in ("مشروع", "plugin")


def test_vim_mode_env_read(monkeypatch):
    # نتأكد أن _make_slash_prompt يقرأ WEAVER_VIM دون خطأ (قد يُرجع None بلا prompt_toolkit)
    import weaver

    class _FakeCommands:
        def list_meta(self):
            return []

    monkeypatch.setenv("WEAVER_VIM", "1")
    # لا يجب أن يرمي استثناءً
    result = weaver._make_slash_prompt(_FakeCommands())
    assert result is None or result is not None  # مجرد عدم رمي استثناء


# ── 4) امتداد VS Code (ملفات حقيقية) ─────────────────────────────────────────

_IDE = Path(__file__).resolve().parent.parent / "ide" / "vscode"


def test_vscode_package_json_valid():
    pkg = json.loads((_IDE / "package.json").read_text(encoding="utf-8"))
    assert pkg["name"] == "weavercode"
    assert "main" in pkg
    cmds = [c["command"] for c in pkg["contributes"]["commands"]]
    for expected in ("weavercode.openChat", "weavercode.runTask",
                     "weavercode.runSelection", "weavercode.explainFile"):
        assert expected in cmds


def test_vscode_extension_js_exists():
    ext = _IDE / "extension.js"
    assert ext.exists()
    src = ext.read_text(encoding="utf-8")
    # يصدّر activate/deactivate
    assert "function activate" in src
    assert "function deactivate" in src
    assert "module.exports" in src
    # اقتباس آمن للـ shell موجود
    assert "shellQuote" in src


def test_vscode_readme_exists():
    assert (_IDE / "README.md").exists()
