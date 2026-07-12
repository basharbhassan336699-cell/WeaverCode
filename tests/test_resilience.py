"""اختبارات الصمود: إعادة المحاولة التلقائية والمزوّد الاحتياطي."""

import asyncio
from core.engine.provider import (WeaverProvider, ResilientProvider, ProviderConfig,
                                  Message, ProviderError, TransientProviderError)


def _prov(retries=2):
    return WeaverProvider(ProviderConfig(api_key="k", base_url="http://x",
                                         model="m", retries=retries, retry_base=0))


def test_retry_recovers_after_transient():
    p = _prov(retries=2)
    calls = {"n": 0}

    async def once(url, payload):
        calls["n"] += 1
        if calls["n"] < 3:
            raise TransientProviderError("عابر")
        return {"ok": True}

    p._run_curl_once = once
    assert asyncio.run(p._run_curl("u", {})) == {"ok": True}
    assert calls["n"] == 3  # حاول 3 مرات (1 + 2 إعادة)


def test_permanent_error_not_retried():
    p = _prov(retries=3)
    calls = {"n": 0}

    async def once(url, payload):
        calls["n"] += 1
        raise ProviderError("دائم")

    p._run_curl_once = once
    try:
        asyncio.run(p._run_curl("u", {}))
        assert False
    except ProviderError:
        pass
    assert calls["n"] == 1  # لا إعادة للأخطاء الدائمة


class _Dead:
    config = ProviderConfig(api_key="k", base_url="http://dead", model="m")

    async def complete(self, m, tools=None):
        raise ProviderError("نفد الرصيد")

    async def stream_events(self, m, tools=None):
        raise ProviderError("نفد الرصيد")
        yield  # pragma: no cover


class _Live:
    config = ProviderConfig(api_key="k", base_url="http://live", model="m")

    async def complete(self, m, tools=None):
        return {"choices": [{"message": {"content": "احتياطي"}, "finish_reason": "stop"}]}

    async def stream_events(self, m, tools=None):
        yield {"type": "text", "text": "احتياطي"}
        yield {"type": "done", "finish_reason": "stop"}


def test_fallback_switches_to_backup():
    rp = ResilientProvider([_Dead(), _Live()])
    r = asyncio.run(rp.complete([Message(role="user", content="hi")]))
    assert r["choices"][0]["message"]["content"] == "احتياطي"


def test_fallback_stream_switches():
    rp = ResilientProvider([_Dead(), _Live()])

    async def collect():
        out = ""
        async for ev in rp.stream_events([Message(role="user", content="hi")]):
            if ev["type"] == "text":
                out += ev["text"]
        return out

    assert asyncio.run(collect()) == "احتياطي"


def test_all_providers_fail_aggregated():
    rp = ResilientProvider([_Dead(), _Dead()])
    try:
        asyncio.run(rp.complete([Message(role="user", content="hi")]))
        assert False
    except ProviderError as e:
        assert "فشل كل المزوّدين" in str(e)


def test_get_provider_builds_chain(monkeypatch):
    from core.engine.provider import get_provider
    monkeypatch.setenv("WEAVER_FALLBACK_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("WEAVER_FALLBACK_API_KEY", "gsk_test")
    monkeypatch.setenv("WEAVER_FALLBACK_MODEL", "llama-3.3-70b-versatile")
    prov = get_provider(api_key="k", base_url="https://capi.aerolink.lat",
                        model="claude-fable-5")
    assert isinstance(prov, ResilientProvider)
    assert len(prov.providers) == 2
