"""
اختبارات ضبط السرعة: أوصاف أدوات مختصرة (compact) بلا إسقاط أدوات،
وحدّ max_turns القابل للضبط عبر البيئة.
"""

import json
import os


def test_compact_schema_keeps_all_tools():
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir="/tmp")
    full = reg.get_schema(compact=False)
    comp = reg.get_schema(compact=True)
    assert len(full) == len(comp)  # لا أداة تسقط
    names_full = {t["function"]["name"] for t in full}
    names_comp = {t["function"]["name"] for t in comp}
    assert names_full == names_comp


def test_compact_shortens_descriptions():
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir="/tmp")
    comp = reg.get_schema(compact=True)
    for t in comp:
        assert len(t["function"]["description"]) <= 100
    # الحجم الإجمالي أصغر أو مساوٍ
    full_s = json.dumps(reg.get_schema(compact=False), ensure_ascii=False)
    comp_s = json.dumps(comp, ensure_ascii=False)
    assert len(comp_s) <= len(full_s)


def test_compact_reads_env(monkeypatch):
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir="/tmp")
    monkeypatch.setenv("WEAVER_COMPACT_TOOLS", "1")
    env_on = json.dumps(reg.get_schema(), ensure_ascii=False)
    monkeypatch.setenv("WEAVER_COMPACT_TOOLS", "0")
    env_off = json.dumps(reg.get_schema(), ensure_ascii=False)
    assert len(env_on) <= len(env_off)


def test_compact_preserves_required_params():
    """الاختصار لا يمسّ بنية الوسائط المطلوبة — فقط أطوال الأوصاف."""
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir="/tmp")
    comp = {t["function"]["name"]: t for t in reg.get_schema(compact=True)}
    write = comp["Write"]["function"]["parameters"]
    assert "path" in write["properties"]
    assert "content" in write["properties"]
    assert set(write.get("required", [])) == {"path", "content"}


def test_max_turns_env_override(monkeypatch):
    from core.engine.query_engine import QueryEngine
    from core.tools.registry import ToolRegistry

    class _P:
        class config:
            model = "m"
    import core.engine.query_engine as qe
    monkeypatch.setenv("WEAVER_MAX_TURNS", "7")
    e = object.__new__(qe.QueryEngine)
    e.__init__(provider=_P(), tool_registry=ToolRegistry(work_dir="/tmp"))
    assert e.max_turns == 7


def test_max_turns_explicit_wins(monkeypatch):
    from core.engine.query_engine import QueryEngine
    from core.tools.registry import ToolRegistry

    class _P:
        class config:
            model = "m"
    import core.engine.query_engine as qe
    monkeypatch.setenv("WEAVER_MAX_TURNS", "7")
    e = object.__new__(qe.QueryEngine)
    e.__init__(provider=_P(), tool_registry=ToolRegistry(work_dir="/tmp"), max_turns=50)
    assert e.max_turns == 50


def test_todowrite_description_advises_restraint():
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir="/tmp")
    td = reg.get_tool("TodoWrite")
    assert "باعتدال" in td.description or "لا تحدّثه بعد كل خطوة" in td.description
