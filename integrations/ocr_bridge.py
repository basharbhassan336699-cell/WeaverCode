"""
ocr_bridge.py — جسر WeaverCode إلى أدوات OCR المدمجة (olmOCR / Chandra) 🕸️
=========================================================================
Thin bridge to the vendored OCR tools in ``vendors/``. WeaverCode never imports
the heavy OCR stacks directly — it shells out to them as separate processes, so
their large dependencies (torch, vLLM, boto3, …) are only needed when the tools
are actually run. Every function degrades gracefully with a clear message when a
tool or its dependencies are missing, and never modifies anything under
``vendors/``.

Public API:
    run_olmocr(file_path, workspace, server_url) -> str
    run_chandra(file_path, server_url=None, method="vllm") -> dict
    detect_file_type(file_path) -> dict
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Optional

# جذر المشروع ومجلد الأدوات المدمجة
_ROOT = Path(__file__).resolve().parent.parent
_VENDORS = _ROOT / "vendors"
_OLMOCR_DIR = _VENDORS / "olmocr"
_CHANDRA_DIR = _VENDORS / "chandra"

# امتدادات الملفات لكل فئة → الأداة الموصى بها
_PDF_EXT = {".pdf"}
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tiff", ".tif", ".bmp"}


class OcrBridgeError(RuntimeError):
    """خطأ في تشغيل أداة OCR مدمجة (أداة/تبعية مفقودة أو فشل تنفيذ)."""


# ── أدوات مساعدة ─────────────────────────────────────────────────────────────

def _env_with_pythonpath(extra_path: Path) -> Dict[str, str]:
    """بيئة مع إضافة مسار حزمة مدمجة إلى PYTHONPATH (ليُستورَد دون تثبيت)."""
    env = dict(os.environ)
    prev = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (str(extra_path) + (os.pathsep + prev if prev else ""))
    return env


def _run(cmd, cwd=None, env=None, timeout=1800) -> subprocess.CompletedProcess:
    """تشغيل عملية مع التقاط المخرجات، وترجمة الأخطاء الشائعة لرسائل واضحة."""
    try:
        return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=timeout)
    except FileNotFoundError as e:
        raise OcrBridgeError(f"البرنامج غير مثبّت: {cmd[0]} ({e})") from e
    except subprocess.TimeoutExpired as e:
        raise OcrBridgeError(f"انتهت مهلة التشغيل بعد {timeout}s") from e


def _read_first_markdown(search_dir: Path, stem: str) -> Optional[str]:
    """يقرأ أول ملف Markdown ناتج (يفضّل المطابق لاسم الملف الأصلي)."""
    if not search_dir.exists():
        return None
    mds = sorted(search_dir.rglob("*.md"))
    if not mds:
        return None
    # فضّل الملف الذي يحمل اسم المصدر
    for m in mds:
        if m.stem == stem:
            return m.read_text(encoding="utf-8", errors="replace")
    return mds[0].read_text(encoding="utf-8", errors="replace")


# ── olmOCR ───────────────────────────────────────────────────────────────────

def run_olmocr(file_path: str, workspace: str, server_url: str) -> str:
    """يشغّل olmOCR على ملف PDF ويُعيد النصّ (Markdown) المستخرَج.

    file_path  : مسار ملف PDF (محلي).
    workspace  : مجلد عمل olmOCR (يُنشَأ إن لم يوجد) — تُكتب فيه النتائج.
    server_url : رابط خادم vLLM المتوافق (مثل http://host:port/v1). إلزامي —
                 olmOCR يتطلّب خادم استدلال يعمل.

    يُرجع: نصّ Markdown المستخرَج (str).
    يرمي OcrBridgeError عند فشل التشغيل أو غياب المخرجات.
    """
    src = Path(file_path).expanduser().resolve()
    if not src.exists():
        raise OcrBridgeError(f"الملف غير موجود: {file_path}")
    if not server_url:
        raise OcrBridgeError("olmOCR يتطلّب server_url (رابط خادم vLLM).")
    ws = Path(workspace).expanduser().resolve()
    ws.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "olmocr.pipeline", str(ws),
           "--pdfs", str(src), "--markdown", "--server", server_url]
    proc = _run(cmd, cwd=str(_OLMOCR_DIR),
                env=_env_with_pythonpath(_OLMOCR_DIR))
    if proc.returncode != 0:
        raise OcrBridgeError(
            "فشل olmOCR (تحقّق من التبعيات وخادم vLLM):\n"
            + (proc.stderr or proc.stdout or "").strip()[:600])

    text = _read_first_markdown(ws / "markdown", src.stem)
    if text is None:
        raise OcrBridgeError(
            "اكتمل olmOCR لكن لم يُعثر على مخرجات Markdown في "
            f"{ws / 'markdown'}")
    return text


# ── Chandra ──────────────────────────────────────────────────────────────────

def run_chandra(file_path: str, server_url: Optional[str] = None,
                method: str = "vllm") -> Dict:
    """يشغّل Chandra على ملف (PDF/صورة) ويُعيد النتيجة.

    file_path  : مسار الملف (PDF أو صورة مدعومة).
    server_url : رابط خادم vLLM (يُمرَّر عبر VLLM_API_BASE). يلزم مع method=vllm.
    method     : "vllm" (خادم) أو "hf" (نموذج محلي).

    يُرجع dict: {tool, method, text, markdown_path, output_dir}.
    يرمي OcrBridgeError عند فشل التشغيل أو غياب المخرجات.
    """
    src = Path(file_path).expanduser().resolve()
    if not src.exists():
        raise OcrBridgeError(f"الملف غير موجود: {file_path}")
    method = (method or "vllm").lower()
    if method not in ("vllm", "hf"):
        raise OcrBridgeError(f"method غير مدعوم: {method} (المتاح: vllm|hf)")

    out_dir = Path(tempfile.mkdtemp(prefix="chandra_"))
    env = _env_with_pythonpath(_CHANDRA_DIR)
    if server_url:
        env["VLLM_API_BASE"] = server_url

    cmd = [sys.executable, "-m", "chandra.scripts.cli",
           str(src), str(out_dir), "--method", method]
    proc = _run(cmd, cwd=str(_CHANDRA_DIR), env=env)
    if proc.returncode != 0:
        raise OcrBridgeError(
            "فشل Chandra (تحقّق من التبعيات/الخادم):\n"
            + (proc.stderr or proc.stdout or "").strip()[:600])

    mds = sorted(out_dir.rglob("*.md"))
    text = _read_first_markdown(out_dir, src.stem)
    return {
        "tool": "chandra",
        "method": method,
        "text": text or "",
        "markdown_path": str(mds[0]) if mds else None,
        "output_dir": str(out_dir),
    }


# ── الكشف التلقائي عن الأداة المناسبة ────────────────────────────────────────

def detect_file_type(file_path: str) -> Dict:
    """يحدّد تلقائياً أيّ أداة OCR تناسب الملف بناءً على نوعه.

    القاعدة: PDF → olmOCR (متخصّص في المستندات الطويلة عبر vLLM)،
    الصور → Chandra (يقبل الصور مباشرةً). غير المدعوم → tool=None.

    يُرجع dict: {ext, category, tool, reason}.
    """
    ext = Path(file_path).suffix.lower()
    if ext in _PDF_EXT:
        return {"ext": ext, "category": "pdf", "tool": "olmocr",
                "reason": "PDF → olmOCR (خطّ أنابيب مستندات على vLLM)"}
    if ext in _IMAGE_EXT:
        return {"ext": ext, "category": "image", "tool": "chandra",
                "reason": "صورة → Chandra (يقبل الصور مباشرةً)"}
    return {"ext": ext, "category": "unsupported", "tool": None,
            "reason": f"امتداد غير مدعوم للـ OCR: {ext or '(بلا امتداد)'}"}
