"""
integrations — جسور WeaverCode إلى الأدوات المدمجة في vendors/ 🕸️
================================================================
يعرض دوال الجسور مباشرةً للاستيراد المريح:

    from integrations import (
        run_olmocr, run_chandra, detect_file_type,   # OCR (olmOCR / Chandra)
        audit_project, check_gate, check_context,     # Loop Engineering
    )

الجسور رقيقة: تُشغّل الأدوات كعمليات منفصلة (subprocess) ولا تُعدّل أيّ شيء داخل
vendors/. أخطاء التشغيل تُرفَع كـ OcrBridgeError / LoopBridgeError برسائل واضحة.
"""
from .ocr_bridge import (
    OcrBridgeError,
    detect_file_type,
    run_chandra,
    run_olmocr,
)
from .loop_bridge import (
    LoopBridgeError,
    audit_project,
    check_context,
    check_gate,
)

__all__ = [
    # OCR
    "run_olmocr",
    "run_chandra",
    "detect_file_type",
    "OcrBridgeError",
    # Loop Engineering
    "audit_project",
    "check_gate",
    "check_context",
    "LoopBridgeError",
]
