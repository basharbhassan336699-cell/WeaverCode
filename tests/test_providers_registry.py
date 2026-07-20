"""
اختبارات سجل المزوّدين المدفوع بالبيانات + كشف المنصة العام (بادئة + سبر).
حل جذري: أي منصة تُدخل مفتاحها يُكتشف رابطها — لا تخصيص لمنصة في المنطق.
"""

import pathlib

from core import providers


def test_registry_default_platforms():
    names = providers.provider_names()
    for n in ("openai", "anthropic", "nvidia", "groq", "openrouter",
              "deepseek", "together", "mistral", "aerolink", "ollama"):
        assert n in names


def test_detect_by_prefix_distinctive():
    assert providers.detect_by_prefix("nvapi-x")["name"] == "nvidia"
    assert providers.detect_by_prefix("sk-ant-x")["name"] == "anthropic"
    assert providers.detect_by_prefix("gsk_x")["name"] == "groq"
    assert providers.detect_by_prefix("xai-x")["name"] == "xai"
    assert providers.detect_by_prefix("pplx-x")["name"] == "perplexity"


def test_detect_by_prefix_generic_is_none():
    # مفتاح عام (بوابة) لا يُطابق بادئة → None (لا كسر لإعداد قائم)
    assert providers.detect_by_prefix("randomgatewaykey") is None


def test_resolve_by_prefix_verified():
    def http(url, headers, timeout=8):
        if "nvidia.com" in url:
            return {"data": [{"id": "meta/llama-3.1-70b-instruct"}]}, None
        return None, "401"

    e = providers.resolve_platform("nvapi-abc", http, current_base="https://old/v1")
    assert e["name"] == "nvidia" and e["models"]


def test_resolve_by_probe_for_generic_key():
    """مفتاح عام بلا بادئة → يُكتشف بسبر نقاط /models للسجل."""
    def http(url, headers, timeout=8):
        if "deepseek.com" in url and url.endswith("/models"):
            return {"data": [{"id": "deepseek-chat"}]}, None
        return None, "401"

    e = providers.resolve_platform("sk-generic", http,
                                   current_base="https://capi.aerolink.lat/v1")
    assert e["name"] == "deepseek"


def test_resolve_keeps_current_when_valid():
    """الرابط الحالي يعمل بالمفتاح → لا تبديل (يُرجع None)."""
    def http(url, headers, timeout=8):
        if "aerolink" in url:
            return {"data": [{"id": "claude-fable-5"}]}, None
        return None, "401"

    e = providers.resolve_platform("anykey", http,
                                   current_base="https://capi.aerolink.lat/v1")
    assert e is None


def test_resolve_none_when_nothing_works():
    e = providers.resolve_platform("badkey", lambda u, h, t=8: (None, "401"),
                                   current_base="https://x/v1")
    assert e is None


def test_add_provider_extensible(tmp_path, monkeypatch):
    monkeypatch.setattr(providers, "_USER_REGISTRY", tmp_path / "providers.json")
    assert providers.add_provider("acme", "https://api.acme.ai/v1",
                                  model="acme-1", prefixes=["acme-"])
    assert providers.get_provider("acme")["base_url"] == "https://api.acme.ai/v1"
    assert providers.detect_by_prefix("acme-key")["name"] == "acme"


def test_models_urls_normalizes_v1():
    urls = providers.models_urls("https://x.ai/v1")
    assert "https://x.ai/v1/models" in urls
    assert "https://x.ai/models" in urls
