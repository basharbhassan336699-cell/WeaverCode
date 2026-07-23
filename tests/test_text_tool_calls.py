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


def test_param_with_extra_attributes_string_true():
    """صيغة اللقطات الفعلية: <parameter name="command" string="true">…</parameter>."""
    import json
    text = ('<|DSML|>\n<invoke name="Bash">\n'
            '<parameter name="command" string="true">find /x -type f | head -5</parameter>\n'
            '<parameter name="description" string="true">عرض الملفات</parameter>\n'
            '</invoke>\n<|DSML|>')
    calls = _extract_text_tool_calls(text)
    assert len(calls) == 1
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["command"] == "find /x -type f | head -5"
    assert args["description"] == "عرض الملفات"


def test_write_with_multiline_yaml_content():
    """Write بمحتوى YAML متعدد الأسطر (لقطة config.yaml) — يُستخرج كاملاً."""
    import json
    text = ('<invoke name="Write">\n'
            '<parameter name="file_path" string="true">/w/config/config.yaml</parameter>\n'
            '<parameter name="content" string="true"># Config\n'
            'project:\n  name: "Weaver-Write"\n  version: "0.1.0"</parameter>\n'
            '</invoke>')
    calls = _extract_text_tool_calls(text)
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["path"] == "/w/config/config.yaml"
    assert 'name: "Weaver-Write"' in args["content"]
    assert len(args["content"].splitlines()) == 4


def test_think_tag_stripped_from_head():
    head, calls = _apply_text_tool_calls(
        'سأبدأ الآن.<think/>\n<invoke name="Bash">'
        '<parameter name="command" string="true">ls</parameter></invoke>')
    assert calls is not None
    assert head == "سأبدأ الآن."
    assert "<think" not in head


def test_json_tool_calls_extracted():
    """صيغ JSON المضمّنة: {"tool": ...} و {"name": ..., "arguments": {...}}."""
    import json as _j
    from core.engine.provider import _extract_json_tool_calls
    r = _extract_json_tool_calls('سأنفذ: {"tool": "Bash", "args": {"command": "ls"}}')
    assert r and r[0]["function"]["name"] == "Bash"
    assert _j.loads(r[0]["function"]["arguments"])["command"] == "ls"
    r2 = _extract_json_tool_calls(
        '{"name": "Write", "arguments": {"path": "t.py", "content": "hi"}}')
    assert r2 and r2[0]["function"]["name"] == "Write"


def test_json_plain_object_not_captured():
    """تحصين: JSON عادي في الشرح (name بلا مفتاح وسائط) لا يُلتقط كأداة."""
    from core.engine.provider import _extract_json_tool_calls
    assert _extract_json_tool_calls(
        'المشروع: {"name": "Weaver-Write", "version": "0.1.0"}') == []


def test_text_extractor_falls_back_to_json():
    calls = _extract_text_tool_calls(
        'تنفيذ: {"tool": "Read", "args": {"path": "a.md"}}')
    assert calls and calls[0]["function"]["name"] == "Read"


def test_stop_finish_with_native_tool_calls_still_executes():
    """نماذج تُرجع finish_reason=stop مع tool_calls أصلية → تُنفَّذ لا تُتجاهَل."""
    resp = WeaverProvider._anthropic_to_openai_response({
        "choices": [{"message": {"role": "assistant", "content": "",
                                 "tool_calls": [{"id": "t1", "type": "function",
                                                 "function": {"name": "Bash",
                                                              "arguments": "{}"}}]},
                     "finish_reason": "stop"}]})
    assert resp["choices"][0]["finish_reason"] == "tool_calls"


def test_json_head_preserves_prose():
    from core.engine.provider import _apply_text_tool_calls
    head, calls = _apply_text_tool_calls(
        'سأنفّذ الأمر الآن: {"tool": "Bash", "args": {"command": "pwd"}}')
    assert calls is not None
    assert head == "سأنفّذ الأمر الآن:"


def test_native_tool_calls_not_overridden():
    """إن كانت هناك tool_calls أصلية، لا نلمسها."""
    resp = WeaverProvider._anthropic_to_openai_response({
        "content": [{"type": "tool_use", "id": "x", "name": "Write",
                     "input": {"path": "a"}}],
        "stop_reason": "tool_use"})
    assert resp["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "Write"
