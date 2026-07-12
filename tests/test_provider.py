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
    a = _p("https://capi.aerolink.lat")._headers()
    assert a["x-api-key"] == "k" and a["anthropic-version"] == "2023-06-01"
    o = _p("https://api.groq.com/openai/v1")._headers()
    assert o["Authorization"] == "Bearer k" and "x-api-key" not in o


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
