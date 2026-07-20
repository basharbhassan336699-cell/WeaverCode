"""
اختبارات استخراج استدعاءات الأدوات المكتوبة كنصّ (<invoke name="...">) وتنفيذها.
يعالج: النموذج يكتب الأدوات ككود نصّي ويقول «اكتملت» دون تنفيذ (فشل البناء).
"""

from core.engine.provider import (WeaverProvider, _extract_text_tool_calls,
                                  _apply_text_tool_calls)


_SAMPLE = '''لنبدأ بالتنفيذ:

<|DSML|>
<invoke name="Bash">
<parameter name="command">mkdir -p src/{core,modules,utils} tests docs</parameter>
<parameter name="description">إنشاء الهيكل</parameter>
</invoke>
<invoke name="Read">
<parameter name="filePath">README.md</parameter>
</invoke>
<|DSML|>'''


def test_extract_two_tool_calls():
    calls = _extract_text_tool_calls(_SAMPLE)
    assert len(calls) == 2
    assert calls[0]["function"]["name"] == "Bash"
    assert calls[1]["function"]["name"] == "Read"


def test_param_alias_filepath_to_path():
    import json
    calls = _extract_text_tool_calls(_SAMPLE)
    args = json.loads(calls[1]["function"]["arguments"])
    assert args["path"] == "README.md"  # filePath → path


def test_bash_command_extracted():
    import json
    calls = _extract_text_tool_calls(_SAMPLE)
    args = json.loads(calls[0]["function"]["arguments"])
    assert "mkdir -p" in args["command"]


def test_apply_keeps_prose_head():
    head, calls = _apply_text_tool_calls(_SAMPLE)
    assert head == "لنبدأ بالتنفيذ:"
    assert calls and len(calls) == 2


def test_no_invoke_returns_empty():
    assert _extract_text_tool_calls("مجرد نص عادي بلا أدوات") == []
    head, calls = _apply_text_tool_calls("رد عادي")
    assert calls is None and head == "رد عادي"


def test_full_response_sets_tool_calls_and_finish():
    resp = WeaverProvider._anthropic_to_openai_response({
        "choices": [{"message": {"role": "assistant", "content": _SAMPLE},
                     "finish_reason": "stop"}]})
    ch = resp["choices"][0]
    assert ch["finish_reason"] == "tool_calls"  # لا "stop" رغم أن الأصل stop
    assert len(ch["message"]["tool_calls"]) == 2
    assert ch["message"]["content"] == "لنبدأ بالتنفيذ:"


def test_clean_param_strips_type_prefix():
    import json
    text = '<invoke name="Bash"><parameter name="command">string="true">ls -la</parameter></invoke>'
    calls = _extract_text_tool_calls(text)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["command"] == "ls -la"  # نُزعت بادئة string="true">


def test_native_tool_calls_not_overridden():
    """إن كانت هناك tool_calls أصلية، لا نلمسها."""
    resp = WeaverProvider._anthropic_to_openai_response({
        "content": [{"type": "tool_use", "id": "x", "name": "Write",
                     "input": {"path": "a"}}],
        "stop_reason": "tool_use"})
    assert resp["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "Write"
