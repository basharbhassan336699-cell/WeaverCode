"""
اختبارات ذاكرة تكيّف المزوّد: drop_tools/bare_mode قيود لحظية للجلسة —
لا تُورَّث من الكاش ولا تُحفَظ فيه (السبب الجذري لكتابة الأدوات نصاً DSML).
"""

import json
import os

import pytest

from core.engine.provider import WeaverProvider, ProviderConfig


@pytest.fixture
def poisoned_cache(tmp_path, monkeypatch):
    """كاش فاسد يحاكي جهازاً ورث drop_tools=true من فشل قديم."""
    cache = tmp_path / "provider_cache.json"
    cache.write_text(json.dumps({
        "https://capi.aerolink.lat/v1": {
            "drop_tools": True, "bare_mode": True,
            "format_override": True, "max_tokens": 4096}}))
    monkeypatch.setenv("WEAVER_PROVIDER_CACHE", str(cache))
    return cache


def _prov():
    return WeaverProvider(ProviderConfig(
        api_key="x", base_url="https://capi.aerolink.lat/v1", model="m"))


def test_drop_tools_not_inherited_from_cache(poisoned_cache):
    p = _prov()
    assert p._drop_tools is False
    assert p._bare_mode is False


def test_useful_quirks_still_inherited(poisoned_cache):
    p = _prov()
    assert p._format_override is True          # الصيغة تُورَّث (مفيدة وغير مقيّدة)
    assert p.config.max_tokens <= 4096         # وسقف التوكنات كذلك


def test_drop_tools_not_persisted(poisoned_cache):
    p = _prov()
    p._drop_tools = True   # اكتشاف لحظي داخل الجلسة
    p._bare_mode = True
    p._save_quirk_cache()
    saved = json.loads(poisoned_cache.read_text())["https://capi.aerolink.lat/v1"]
    assert "drop_tools" not in saved
    assert "bare_mode" not in saved
    assert "format_override" in saved          # المفيد يبقى محفوظاً


def test_cache_disabled_still_works(monkeypatch):
    monkeypatch.setenv("WEAVER_PROVIDER_CACHE", "off")
    p = _prov()
    assert p._drop_tools is False
    p._save_quirk_cache()  # لا يتعطّل
