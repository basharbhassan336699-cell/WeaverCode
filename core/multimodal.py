"""
multimodal.py — قراءة الوسائط المتعددة (صور / PDF) لـ WeaverCode
================================================================

يوفّر أدوات لاكتشاف ملفات الوسائط (صور، PDF) وترميزها base64 إلى كتل محتوى
بصيغة Anthropic أو OpenAI، حتى يستطيع النموذج (إن كان يدعم الرؤية) تحليلها.

⚠️ لا يمسّ هذا الملف طبقة المصادقة/المفاتيح في provider.py إطلاقاً. هو مجرّد
   مُنتِج لكتل المحتوى؛ قرار إرسالها للنموذج يبقى بيد المستدعي.

EN: Helpers to detect and base64-encode image/PDF files into vision content
blocks (Anthropic or OpenAI shape). Purely a content builder — it does NOT
touch provider auth/keys.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Optional

# امتداد → نوع MIME للصور المدعومة في الرؤية
_IMAGE_MIME = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}

_PDF_MIME = "application/pdf"

# حد أقصى لحجم الملف المُرمَّز (5MB) — تفادي إغراق الطلب
_MAX_BYTES = 5 * 1024 * 1024


def detect_media_type(path: str) -> Optional[str]:
    """يُرجع نوع MIME إن كان الملف صورة/PDF مدعوماً، وإلا None."""
    ext = Path(path).suffix.lower()
    if ext in _IMAGE_MIME:
        return _IMAGE_MIME[ext]
    if ext == ".pdf":
        return _PDF_MIME
    return None


def is_image(path: str) -> bool:
    """هل الملف صورة مدعومة؟"""
    return Path(path).suffix.lower() in _IMAGE_MIME


def is_pdf(path: str) -> bool:
    """هل الملف PDF؟"""
    return Path(path).suffix.lower() == ".pdf"


def is_multimodal(path: str) -> bool:
    """هل الملف من نوع وسائط متعددة (صورة/PDF)؟"""
    return detect_media_type(path) is not None


def encode_base64(path: str) -> str:
    """يقرأ الملف ويُرجع محتواه مُرمَّزاً base64 (نصّاً)."""
    data = Path(path).read_bytes()
    if len(data) > _MAX_BYTES:
        raise ValueError(
            f"الملف كبير جداً للترميز ({len(data)} بايت > {_MAX_BYTES})."
        )
    return base64.b64encode(data).decode("ascii")


def build_anthropic_block(path: str) -> Dict[str, Any]:
    """
    يبني كتلة محتوى بصيغة Anthropic:
        صورة → {"type": "image", "source": {...}}
        PDF   → {"type": "document", "source": {...}}
    """
    media_type = detect_media_type(path)
    if media_type is None:
        raise ValueError(f"نوع غير مدعوم للوسائط: {path}")
    b64 = encode_base64(path)
    kind = "document" if media_type == _PDF_MIME else "image"
    return {
        "type": kind,
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64,
        },
    }


def build_openai_block(path: str) -> Dict[str, Any]:
    """
    يبني كتلة محتوى بصيغة OpenAI (image_url مع data URI).
    ملاحظة: OpenAI vision يدعم الصور؛ الـ PDF يُرمَّز كـ data URI أيضاً.
    """
    media_type = detect_media_type(path)
    if media_type is None:
        raise ValueError(f"نوع غير مدعوم للوسائط: {path}")
    b64 = encode_base64(path)
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{b64}"},
    }


def build_block(path: str, fmt: str = "anthropic") -> Dict[str, Any]:
    """يبني كتلة محتوى وسائط حسب الصيغة المطلوبة ('anthropic' أو 'openai')."""
    if fmt == "openai":
        return build_openai_block(path)
    return build_anthropic_block(path)


def describe(path: str) -> str:
    """
    وصف نصّي مختصر لملف وسائط (للعرض في نتيجة أداة Read غير الرؤيوية).
    يذكر النوع والحجم بالكيلوبايت.
    """
    p = Path(path)
    if not p.exists():
        return f"الملف غير موجود: {path}"
    media_type = detect_media_type(path) or "غير معروف"
    size_kb = p.stat().st_size / 1024
    kind = "PDF" if is_pdf(path) else ("صورة" if is_image(path) else "ملف")
    return (f"📎 {kind}: {p.name}\n"
            f"   النوع: {media_type}\n"
            f"   الحجم: {size_kb:.1f} KB\n"
            f"   (ملف وسائط ثنائي — استُخرجت بياناته الوصفية بدل النص)")
