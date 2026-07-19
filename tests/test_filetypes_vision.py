"""
اختبارات قراءة الملفات بشتى أنواعها + ربط الرؤية (صور) بالنموذج.
تغطّي إصلاح: «الملف يُرفع لكن لا يُقرأ» و«الصورة لا يراها النموذج».
"""

import base64
import os
import zipfile

# PNG صالح 1×1 لاختبار الرؤية
_PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


# ── قراءة الأنواع المختلفة ──────────────────────────────────────────────────

def test_read_text_with_line_numbers(tmp_path):
    from core.filetypes import read_any
    f = tmp_path / "a.py"
    f.write_text("print(1)\nprint(2)")
    out = read_any(str(f))
    assert "1\tprint(1)" in out and "2\tprint(2)" in out


def test_read_csv_as_table(tmp_path):
    from core.filetypes import read_any
    f = tmp_path / "t.csv"
    f.write_text("name,age\nBashar,30")
    out = read_any(str(f))
    assert "Bashar | 30" in out


def test_read_zip_lists_and_extracts_text(tmp_path):
    from core.filetypes import read_any
    z = tmp_path / "z.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("hello.txt", "hi there")
        zf.writestr("code.js", "const x=1;")
    out = read_any(str(z))
    assert "hello.txt" in out and "hi there" in out and "const x=1;" in out


def test_read_docx_extracts_text(tmp_path):
    from core.filetypes import read_any
    docx = tmp_path / "d.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr("word/document.xml",
                    "<w:document><w:body><w:t>مرحبا بالعالم</w:t></w:body></w:document>")
    out = read_any(str(docx))
    assert "مرحبا بالعالم" in out


def test_read_binary_hex_preview(tmp_path):
    from core.filetypes import read_any
    b = tmp_path / "b.bin"
    b.write_bytes(bytes(range(64)))
    out = read_any(str(b))
    assert "ثنائي" in out and "0000" in out


def test_extract_archive_roundtrip(tmp_path):
    from core.filetypes import extract_archive
    z = tmp_path / "z.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/b.txt", "data")
    dest = tmp_path / "out"
    res = extract_archive(str(z), str(dest))
    assert "✅" in res
    assert (dest / "a" / "b.txt").read_text() == "data"


def test_extract_archive_blocks_zip_slip(tmp_path):
    """مسار هروب (../) يُتجاهَل ولا يُكتب خارج مجلد الوجهة."""
    from core.filetypes import extract_archive
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../escape.txt", "pwned")
    dest = tmp_path / "safe"
    extract_archive(str(z), str(dest))
    assert not (tmp_path / "escape.txt").exists()


# ── ربط الرؤية: اكتشاف مسارات الصور وبناء كتل المحتوى ────────────────────────

def test_extract_media_paths_finds_image(tmp_path):
    from core.engine.query_engine import _extract_media_paths
    img = tmp_path / "pic.png"
    img.write_bytes(_PNG_1x1)
    found = _extract_media_paths(f"حلّل هذه الصورة: {img}", str(tmp_path))
    assert str(img) in found


def test_extract_media_paths_ignores_text_files(tmp_path):
    from core.engine.query_engine import _extract_media_paths
    txt = tmp_path / "notes.txt"
    txt.write_text("hi")
    found = _extract_media_paths(f"اقرأ {txt}", str(tmp_path))
    assert found == []


def test_anthropic_payload_embeds_image_block(tmp_path):
    from core.engine.provider import WeaverProvider, ProviderConfig, Message
    img = tmp_path / "pic.png"
    img.write_bytes(_PNG_1x1)
    p = WeaverProvider(ProviderConfig(api_key="x",
                                      base_url="https://api.anthropic.com/v1",
                                      model="claude-fable-5"))
    msgs = [Message(role="user", content="صف الصورة", media=[str(img)])]
    payload = p._build_anthropic_payload(msgs, tools=None)
    content = payload["messages"][0]["content"]
    assert isinstance(content, list)
    assert any(b["type"] == "image" for b in content)
    assert any(b["type"] == "text" for b in content)


def test_openai_payload_embeds_image_block(tmp_path):
    from core.engine.provider import WeaverProvider, ProviderConfig, Message
    img = tmp_path / "pic.png"
    img.write_bytes(_PNG_1x1)
    p = WeaverProvider(ProviderConfig(api_key="x",
                                      base_url="https://api.openai.com/v1",
                                      model="gpt-4o"))
    msgs = [Message(role="user", content="describe", media=[str(img)])]
    payload = p._build_openai_payload(msgs, tools=None)
    content = payload["messages"][0]["content"]
    assert isinstance(content, list)
    assert any(b["type"] == "image_url" for b in content)


def test_message_without_media_stays_string(tmp_path):
    """رسالة بلا وسائط تبقى نصّاً عادياً (عدم كسر السلوك الحالي)."""
    from core.engine.provider import WeaverProvider, ProviderConfig, Message
    p = WeaverProvider(ProviderConfig(api_key="x",
                                      base_url="https://api.anthropic.com/v1",
                                      model="claude-fable-5"))
    payload = p._build_anthropic_payload([Message(role="user", content="مرحبا")], tools=None)
    assert payload["messages"][0]["content"] == "مرحبا"


# ── أدوات السجل: WriteBinary / ExtractArchive / Read الذكية ─────────────────

def test_registry_write_binary_creates_file(tmp_path):
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir=str(tmp_path))
    b64 = base64.b64encode(b"\x89PNG binary").decode()
    res = reg._write_binary("out/img.png", b64)
    assert "✅" in res
    assert (tmp_path / "out" / "img.png").read_bytes() == b"\x89PNG binary"


def test_registry_read_handles_zip(tmp_path):
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir=str(tmp_path))
    z = tmp_path / "z.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("readme.md", "# hi")
    out = reg._read(str(z))
    assert "readme.md" in out


def test_registry_has_new_tools():
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry()
    names = reg.names()
    assert "WriteBinary" in names
    assert "ExtractArchive" in names


def test_registry_extract_archive_tool(tmp_path):
    from core.tools.registry import ToolRegistry
    reg = ToolRegistry(work_dir=str(tmp_path))
    z = tmp_path / "a.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("f.txt", "x")
    res = reg._extract_archive("a.zip", "dest")
    assert "✅" in res
    assert (tmp_path / "dest" / "f.txt").exists()


# ── حقن محتوى المرفقات مباشرةً (يعالج «سأقرأ الملف» دون قراءة فعلية) ─────────

def test_extract_readable_paths_separates_media(tmp_path):
    from core.engine.query_engine import _extract_readable_paths
    html = tmp_path / "page.html"
    html.write_text("<h1>hi</h1>")
    img = tmp_path / "pic.png"
    img.write_bytes(_PNG_1x1)
    readable = _extract_readable_paths(f"اقرأ {html} و {img}", str(tmp_path))
    assert str(html) in readable
    assert str(img) not in readable  # الصورة ليست ملفاً نصياً


def test_materialize_attachments_inlines_html(tmp_path):
    from core.engine.query_engine import _materialize_attachments
    html = tmp_path / "page.html"
    html.write_text("<h1>عنوان</h1><p>محتوى</p>")
    out = _materialize_attachments([str(html)])
    assert "page.html" in out and "عنوان" in out and "محتوى" in out


def test_materialize_attachments_inlines_zip(tmp_path):
    from core.engine.query_engine import _materialize_attachments
    z = tmp_path / "d.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("note.txt", "secret42")
    out = _materialize_attachments([str(z)])
    assert "note.txt" in out and "secret42" in out


def test_materialize_attachments_respects_total_cap(tmp_path):
    from core.engine.query_engine import _materialize_attachments
    big = tmp_path / "big.txt"
    big.write_text("x" * 200000)
    out = _materialize_attachments([str(big)], per_cap=1000, total_cap=1500)
    assert "اقتُطع" in out


def test_materialize_attachments_empty():
    from core.engine.query_engine import _materialize_attachments
    assert _materialize_attachments([]) == ""


# ── النماذج التفكيرية (claude-fable-5): استخراج نصّ الإجابة من كتل thinking ──

def test_thinking_only_response_surfaces_analysis():
    """رد يحوي كتلة تفكير فقط (اقتُطع) → يُعرض التحليل بدل رسالة فارغة."""
    from core.engine.provider import WeaverProvider
    r = WeaverProvider._anthropic_to_openai_response({
        "model": "claude-fable-5", "role": "assistant",
        "content": [{"type": "thinking",
                     "thinking": "في الصورة قطة بيضاء.",
                     "signature": "CAISpw"}],
        "stop_reason": "max_tokens",
    })
    assert "قطة بيضاء" in r["choices"][0]["message"]["content"]


def test_thinking_plus_text_returns_text_only():
    """عند وجود نص فعلي: يُعرض النص لا التفكير (لا تسريب للتفكير الداخلي)."""
    from core.engine.provider import WeaverProvider
    r = WeaverProvider._anthropic_to_openai_response({
        "content": [
            {"type": "thinking", "thinking": "تحليل داخلي", "signature": "x"},
            {"type": "text", "text": "الجواب النهائي"}],
        "stop_reason": "end_turn",
    })
    content = r["choices"][0]["message"]["content"]
    assert content == "الجواب النهائي"
    assert "تحليل داخلي" not in content


def test_thinking_plus_tool_use_preserved():
    from core.engine.provider import WeaverProvider
    r = WeaverProvider._anthropic_to_openai_response({
        "content": [
            {"type": "thinking", "thinking": "t", "signature": "x"},
            {"type": "tool_use", "id": "t1", "name": "Read", "input": {"path": "a"}}],
        "stop_reason": "tool_use",
    })
    msg = r["choices"][0]["message"]
    assert msg.get("tool_calls")
    assert r["choices"][0]["finish_reason"] == "tool_calls"


def test_redacted_thinking_handled():
    from core.engine.provider import WeaverProvider
    r = WeaverProvider._anthropic_to_openai_response({
        "content": [{"type": "redacted_thinking", "text": "محجوب"}],
        "stop_reason": "end_turn",
    })
    # لا يتعطّل؛ يُرجع المحتوى المتاح
    assert isinstance(r["choices"][0]["message"]["content"], str)
