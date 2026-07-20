"""
اختبارات تخزين الأدوات/النظام بالكاش (Anthropic prompt caching) — كما Claude Code.
تُرسَل الأدوات في كل دورة (يحتاجها النموذج) لكن تُقرأ من الكاش لا تُعاد معالجتها.
"""

from core.engine.provider import WeaverProvider, ProviderConfig, Message


def _prov():
    return WeaverProvider(ProviderConfig(
        api_key="x", base_url="https://capi.aerolink.lat/v1", model="claude-fable-5"))


_TOOLS = [
    {"function": {"name": "Read", "description": "d",
                  "parameters": {"type": "object", "properties": {}}}},
    {"function": {"name": "Write", "description": "d",
                  "parameters": {"type": "object", "properties": {}}}},
]
_MSGS = [Message(role="system", content="SYS"), Message(role="user", content="hi")]


def test_cache_control_on_last_tool(monkeypatch):
    monkeypatch.delenv("WEAVER_PROMPT_CACHE", raising=False)
    pl = _prov()._build_anthropic_payload(_MSGS, tools=_TOOLS)
    assert pl["tools"][-1]["cache_control"] == {"type": "ephemeral"}
    # الأدوات الأخرى بلا cache_control (نقطة كسر واحدة تكفي لتخزين الكل)
    assert "cache_control" not in pl["tools"][0]


def test_system_is_cached_block(monkeypatch):
    monkeypatch.delenv("WEAVER_PROMPT_CACHE", raising=False)
    pl = _prov()._build_anthropic_payload(_MSGS, tools=_TOOLS)
    assert isinstance(pl["system"], list)
    assert pl["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert pl["system"][0]["text"] == "SYS"


def test_all_tools_still_sent(monkeypatch):
    """الأدوات لا تُحذف — تبقى كلها تُرسَل ليستطيع النموذج استدعاءها."""
    monkeypatch.delenv("WEAVER_PROMPT_CACHE", raising=False)
    pl = _prov()._build_anthropic_payload(_MSGS, tools=_TOOLS)
    names = {t["name"] for t in pl["tools"]}
    assert names == {"Read", "Write"}


def test_cache_disabled_reverts_cleanly(monkeypatch):
    monkeypatch.setenv("WEAVER_PROMPT_CACHE", "0")
    pl = _prov()._build_anthropic_payload(_MSGS, tools=_TOOLS)
    assert isinstance(pl["system"], str) and pl["system"] == "SYS"
    assert "cache_control" not in pl["tools"][-1]


def test_bare_payload_unaffected(monkeypatch):
    """طلب التعافي العارِي يبقى بلا system/tools/cache (سلوك غير متغيّر)."""
    monkeypatch.delenv("WEAVER_PROMPT_CACHE", raising=False)
    pl = _prov()._build_anthropic_payload(_MSGS, tools=_TOOLS, bare=True)
    assert "system" not in pl and "tools" not in pl
