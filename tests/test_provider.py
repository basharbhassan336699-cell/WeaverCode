"""اختبارات محرّك المزوّد: اكتشاف الصيغة، بناء الـ payload، وتحويل الردود."""

import json
from core.engine.provider import WeaverProvider, ProviderConfig, Message


def _p(url, model="m"):
    return WeaverProvider(ProviderConfig(api_key="k", base_url=url, model=model))


def test_anthropic_detection_by_url():
    assert _p("https://capi.aerolink.lat")._is_anthropic() is True
    assert _p("https://api.anthropic.com/v1")._is_anthropic() is True
    assert _p("https://openrouter.ai/api/v1")._is_anthropic() is False
    assert _p("https://api.groq.com/openai/v1")._is_anthropic() is False


def test_endpoint_url_building():
    assert _p("https://capi.aerolink.lat")._anthropic_url() == \
        "https://capi.aerolink.lat/v1/messages"
    assert _p("https://api.anthropic.com/v1")._anthropic_url() == \
        "https://api.anthropic.com/v1/messages"
    assert _p("https://api.groq.com/openai/v1")._openai_url() == \
        "https://api.groq.com/openai/v1/chat/completions"


def test_headers_per_format():
    # بوابة متوافقة (aerolink): Bearer فقط بلا x-api-key (نطابق ما يعمل يدوياً)
    a = _p("https://capi.aerolink.lat")._headers()
    assert a["anthropic-version"] == "2023-06-01"
    assert a["Authorization"] == "Bearer k" and "x-api-key" not in a
    # Anthropic الرسمي: x-api-key (لا Bearer)
    off = _p("https://api.anthropic.com/v1")._headers()
    assert off["x-api-key"] == "k" and "Authorization" not in off
    # OpenAI: Bearer فقط
    o = _p("https://api.groq.com/openai/v1")._headers()
    assert o["Authorization"] == "Bearer k" and "x-api-key" not in o


def test_305_is_transient_not_json_error():
    """305 (وكل 3xx) يجب أن يُرفع كخطأ عابر واضح لا أن يُعامَل كنجاح ثم يفشل
    عند تحليل JSON (كان يظهر «استجابة ليست JSON صالحاً»)."""
    from core.engine.provider import TransientProviderError
    p = _p("https://capi.aerolink.lat")
    try:
        p._raise_for_status(305, "hiService Unavailable")
        assert False, "should raise"
    except TransientProviderError as e:
        assert "305" in str(e)
    # 2xx يمرّ بلا خطأ
    p._raise_for_status(200, '{"ok":1}')


def test_forced_format_override(monkeypatch):
    monkeypatch.setenv("WEAVER_API_FORMAT", "openai")
    assert _p("https://api.anthropic.com/v1")._is_anthropic() is False
    monkeypatch.setenv("WEAVER_API_FORMAT", "anthropic")
    assert _p("https://api.groq.com/openai/v1")._is_anthropic() is True


def test_anthropic_payload_build_with_tools_and_system():
    p = _p("https://capi.aerolink.lat", "claude-fable-5")
    msgs = [
        Message(role="system", content="أنت WeaverCode"),
        Message(role="user", content="مرحبا"),
        Message(role="assistant", content="",
                tool_calls=[{"id": "t1", "function": {"name": "Read",
                             "arguments": '{"path":"a"}'}}]),
        Message(role="tool", content="محتوى", tool_call_id="t1", name="Read"),
    ]
    tools = [{"type": "function", "function": {"name": "Read", "description": "d",
              "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}}]
    payload = p._build_anthropic_payload(msgs, tools)
    assert payload["system"] == "أنت WeaverCode"
    assert payload["messages"][0] == {"role": "user", "content": "مرحبا"}
    assert payload["messages"][1]["content"][0]["type"] == "tool_use"
    assert payload["messages"][2]["content"][0]["type"] == "tool_result"
    assert payload["tools"][0]["input_schema"]["properties"]["path"]["type"] == "string"


def test_anthropic_text_response_to_openai():
    data = {"id": "m", "content": [{"type": "text", "text": "مرحبا"}],
            "stop_reason": "end_turn"}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    assert conv["choices"][0]["message"]["content"] == "مرحبا"
    assert conv["choices"][0]["finish_reason"] == "stop"


def test_billing_error_hint():
    import json as _json
    p = _p("https://capi.aerolink.lat")
    raw = _json.dumps({"error": "No active free usage is available on this account. "
                                "Add balance or buy a plan to continue."})
    try:
        p._raise_for_status(401, raw)
        assert False, "should raise"
    except Exception as e:
        msg = str(e)
        assert "رصيد" in msg and "مفتاحك" in msg  # يشير للرصيد لا للمفتاح


def test_invalid_key_hint_unchanged():
    import json as _json
    p = _p("https://api.groq.com/openai/v1")
    try:
        p._raise_for_status(401, _json.dumps({"error": "Invalid API key"}))
        assert False
    except Exception as e:
        assert "غير صحيح أو منتهي" in str(e)


def test_anthropic_tool_response_to_openai():
    data = {"id": "m", "stop_reason": "tool_use", "content": [
        {"type": "text", "text": "سأقرأ"},
        {"type": "tool_use", "id": "tu1", "name": "Read", "input": {"path": "x"}}]}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    tc = conv["choices"][0]["message"]["tool_calls"][0]
    assert conv["choices"][0]["finish_reason"] == "tool_calls"
    assert tc["function"]["name"] == "Read"
    assert json.loads(tc["function"]["arguments"]) == {"path": "x"}


# ── صمود تحويل الردود مهما كان شكل الوسيط (سبب "لا يرد النموذج") ──────────────

def test_openai_shaped_response_on_messages_endpoint():
    """بوابات 'capi' المتوافقة تُعيد شكل OpenAI حتى على /v1/messages —
    يجب ألا يضيع النص."""
    data = {"id": "c1", "model": "m", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "مرحبا"}}]}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    assert conv["choices"][0]["message"]["content"] == "مرحبا"
    assert conv["choices"][0]["finish_reason"] == "stop"


def test_openai_shaped_response_with_tool_calls():
    data = {"choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": "",
        "tool_calls": [{"id": "t1", "type": "function",
                        "function": {"name": "Read", "arguments": "{}"}}]}}]}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    assert conv["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "Read"
    assert conv["choices"][0]["finish_reason"] == "tool_calls"


def test_content_as_plain_string():
    """بعض الوسطاء يضعون النص مباشرةً في content كسلسلة لا مصفوفة كتل."""
    data = {"id": "m", "stop_reason": "end_turn", "content": "مرحبا مباشرة"}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    assert conv["choices"][0]["message"]["content"] == "مرحبا مباشرة"


def test_completion_field_fallback():
    """احتياطي: النص في حقل completion/text بدل content."""
    data = {"id": "m", "completion": "نص من completion"}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    assert conv["choices"][0]["message"]["content"] == "نص من completion"


def test_empty_content_stays_empty_no_crash():
    data = {"id": "m", "stop_reason": "end_turn", "content": []}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    assert conv["choices"][0]["message"]["content"] == ""


def test_refusal_is_surfaced_not_empty():
    """رد رفض من النموذج (content فارغ + stop_reason=refusal) يُعرض سببه
    بوضوح بدل تركه فارغاً (حالة aerolink/claude-fable-5 الحقيقية)."""
    data = {"id": "m", "content": [], "stop_reason": "refusal",
            "stop_details": {"type": "refusal", "category": "cyber",
                             "explanation": "blocked under usage policy"}}
    conv = WeaverProvider._anthropic_to_openai_response(data)
    text = conv["choices"][0]["message"]["content"]
    assert "رفض النموذج" in text and "cyber" in text
    # مهم: ليس فارغاً ⇒ لا يُحفّز تبديل الصيغة العبثي
    assert WeaverProvider._response_is_empty(conv) is False


# ── الشفاء الذاتي: تبديل الصيغة تلقائياً (سبب «النموذج لا يرد») ──────────────

def _wrap_openai(text):
    return {"choices": [{"message": {"role": "assistant", "content": text},
                         "finish_reason": "stop"}]}


def test_response_is_empty_detection():
    assert WeaverProvider._response_is_empty(_wrap_openai("")) is True
    assert WeaverProvider._response_is_empty(_wrap_openai("مرحبا")) is False
    with_tools = {"choices": [{"message": {"content": "", "tool_calls": [
        {"id": "t", "type": "function", "function": {"name": "Read", "arguments": "{}"}}]}}]}
    assert WeaverProvider._response_is_empty(with_tools) is False


def test_raise_for_status_sets_metadata():
    p = _p("https://capi.aerolink.lat")
    try:
        p._raise_for_status(404, '{"error":{"message":"Unknown endpoint"}}')
    except Exception as e:
        assert getattr(e, "status", None) == 404 and getattr(e, "billing", None) is False
    try:
        p._raise_for_status(401, '{"error":{"message":"Add balance to continue"}}')
    except Exception as e:
        assert getattr(e, "billing", None) is True


def _make_provider_for_fallback(anthropic_primary=True):
    url = "https://capi.aerolink.lat" if anthropic_primary else "https://api.groq.com/openai/v1"
    return _p(url)


def test_complete_falls_back_on_404(monkeypatch):
    """الصيغة الأساسية تفشل 404 → يُبدَّل تلقائياً للأخرى ويُتذكَّر."""
    from core.engine.provider import ProviderError
    p = _make_provider_for_fallback(anthropic_primary=True)
    assert p._is_anthropic() is True

    async def fake_format(messages, tools, anthropic):
        if anthropic:  # Anthropic غير مدعوم
            err = ProviderError("HTTP 404"); err.status = 404; err.billing = False
            raise err
        return _wrap_openai("مرحبا من OpenAI")

    monkeypatch.setattr(p, "_complete_format", fake_format)
    import asyncio
    resp = asyncio.run(p.complete([Message(role="user", content="hi")]))
    assert resp["choices"][0]["message"]["content"] == "مرحبا من OpenAI"
    assert p._format_override is False  # تعلّم OpenAI
    assert p._is_anthropic() is False   # يستخدمها في الطلبات التالية


def test_complete_falls_back_on_empty(monkeypatch):
    """الصيغة الأساسية ترجع فارغاً → يجرّب الأخرى ويأخذ ردها إن كان غير فارغ."""
    p = _make_provider_for_fallback(anthropic_primary=True)

    async def fake_format(messages, tools, anthropic):
        return _wrap_openai("" if anthropic else "نص بديل")

    monkeypatch.setattr(p, "_complete_format", fake_format)
    import asyncio
    resp = asyncio.run(p.complete([Message(role="user", content="hi")]))
    assert resp["choices"][0]["message"]["content"] == "نص بديل"
    assert p._format_override is False


def test_complete_no_switch_on_billing(monkeypatch):
    """خطأ رصيد/مصادقة → لا يُبدَّل (يفشل بالصيغتين) بل يُرفع الخطأ."""
    from core.engine.provider import ProviderError
    p = _make_provider_for_fallback(anthropic_primary=True)
    calls = {"n": 0}

    async def fake_format(messages, tools, anthropic):
        calls["n"] += 1
        err = ProviderError("HTTP 401"); err.status = 401; err.billing = True
        raise err

    monkeypatch.setattr(p, "_complete_format", fake_format)
    import asyncio
    try:
        asyncio.run(p.complete([Message(role="user", content="hi")]))
        assert False, "should raise"
    except ProviderError:
        pass
    assert calls["n"] == 1  # لم يحاول الصيغة الأخرى


def test_request_too_large_detected_with_limits():
    from core.engine.provider import RequestTooLargeError
    p = _p("https://api.groq.com/openai/v1")
    try:
        p._raise_for_status(413, '{"error":{"message":"Request too large ... '
                            'on tokens per minute (TPM): Limit 12000, Requested 13081, '
                            'please reduce your message size and try again."}}')
        assert False, "should raise"
    except RequestTooLargeError as e:
        assert e.limit == 12000 and e.requested == 13081


def test_complete_shrinks_max_tokens_on_413(monkeypatch):
    """413 (الطلب أكبر من الحدّ) → يقلّل max_tokens تلقائياً ويعيد المحاولة."""
    from core.engine.provider import RequestTooLargeError
    p = _p("https://api.groq.com/openai/v1")
    p.config.max_tokens = 8192
    INPUT = 4889
    LIMIT = 12000

    async def fake_format(messages, tools, anthropic):
        # يحاكي _run_curl داخل _complete_format الحقيقي: نستدعي الأصلي
        raise AssertionError("should not be called")  # لن يُستخدم — نستبدل _run_curl

    async def fake_run_curl(url, payload):
        requested = INPUT + payload["max_tokens"]
        if requested > LIMIT:
            p._raise_for_status(413, json.dumps({"error": {"message":
                f"Request too large tokens per minute (TPM): Limit {LIMIT}, "
                f"Requested {requested}, reduce your message"}}))
        return _wrap_openai(f"ok mt={payload['max_tokens']}")

    monkeypatch.setattr(p, "_run_curl", fake_run_curl)
    import asyncio
    resp = asyncio.run(p.complete([Message(role="user", content="hi")]))
    content = resp["choices"][0]["message"]["content"]
    assert content.startswith("ok mt=")
    assert p.config.max_tokens < 8192  # تعلّم حجماً أصغر
    assert INPUT + p.config.max_tokens <= LIMIT  # يلائم الحدّ فعلاً


def test_complete_drops_tools_on_305(monkeypatch):
    """بوابة ترفض طلبات الأدوات بـ 305 → يُعاد الطلب بلا أدوات ويُتذكَّر ذلك."""
    from core.engine.provider import TransientProviderError
    p = _make_provider_for_fallback(anthropic_primary=True)

    async def fake_format(messages, tools, anthropic):
        if tools:
            err = TransientProviderError("HTTP 305"); err.status = 305
            raise err
        return _wrap_openai("مرحبا بلا أدوات")

    monkeypatch.setattr(p, "_complete_format", fake_format)
    import asyncio
    resp = asyncio.run(p.complete([Message(role="user", content="hi")],
                                  tools=[{"type": "function", "function": {"name": "Read"}}]))
    assert resp["choices"][0]["message"]["content"] == "مرحبا بلا أدوات"
    assert p._drop_tools is True  # تذكّر إسقاط الأدوات لبقية الجلسة


def test_complete_forced_format_no_fallback(monkeypatch):
    """عند تثبيت WEAVER_API_FORMAT: لا تبديل تلقائي إطلاقاً."""
    monkeypatch.setenv("WEAVER_API_FORMAT", "openai")
    p = _make_provider_for_fallback(anthropic_primary=True)
    calls = {"n": 0}

    async def fake_format(messages, tools, anthropic):
        calls["n"] += 1
        assert anthropic is False  # الصيغة المثبّتة فقط
        return _wrap_openai("")  # فارغ لكن لا تبديل

    monkeypatch.setattr(p, "_complete_format", fake_format)
    import asyncio
    asyncio.run(p.complete([Message(role="user", content="hi")]))
    assert calls["n"] == 1
