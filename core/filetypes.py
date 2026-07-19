"""
filetypes.py — قراءة الملفات بشتى أنواعها لـ WeaverCode
=======================================================

يوفّر قراءة نصّية ذكية لأنواع ملفات متعددة دون مكتبات خارجية (مناسب لـ Termux):
نص عادي، JSON/CSV، أرشيفات (zip/tar)، مستندات Office (docx/xlsx/pptx وهي أصلاً
حاويات zip بصيغة XML)، وملفات ثنائية (وصف + معاينة hex).

EN: Dependency-free smart text extraction for many file types (Termux-friendly):
plain text, JSON/CSV, archives (zip/tar), Office docs (docx/xlsx/pptx — which are
zip+XML containers), and binary files (metadata + hex preview).

⚠️ لا يمسّ هذا الملف طبقة المصادقة/المفاتيح إطلاقاً — مجرّد قارئ محتوى.
"""

from __future__ import annotations

import csv
import io
import json
import re
import tarfile
import zipfile
from pathlib import Path
from typing import List

# امتدادات تُعامَل كنصّ صريح مهما كان محتواها
_TEXT_EXT = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".ini", ".cfg", ".conf",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".toml",
    ".html", ".htm", ".css", ".scss", ".xml", ".svg", ".sh", ".bash", ".zsh",
    ".c", ".h", ".cpp", ".hpp", ".cc", ".java", ".kt", ".go", ".rs", ".rb",
    ".php", ".swift", ".sql", ".env", ".gitignore", ".dockerfile", ".makefile",
    ".csv", ".tsv", ".properties", ".gradle", ".lua", ".pl", ".r", ".dart",
}

_ARCHIVE_TAR = {".tar", ".gz", ".tgz", ".bz2", ".tbz", ".xz", ".txz"}
_OFFICE_ZIP = {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}

# حد أقصى للنص المُعاد (تفادي إغراق سياق النموذج)
_MAX_TEXT = 200_000


def _clip(text: str) -> str:
    if len(text) > _MAX_TEXT:
        return text[:_MAX_TEXT] + f"\n\n… [اقتُطع — الحجم الكامل {len(text)} حرف]"
    return text


def _looks_text(sample: bytes) -> bool:
    """تخمين إن كانت البايتات نصّاً (لا تحوي NUL وأغلبها قابل للطباعة)."""
    if b"\x00" in sample:
        return False
    if not sample:
        return True
    printable = sum(1 for b in sample if 9 <= b <= 13 or 32 <= b <= 126 or b >= 128)
    return printable / len(sample) > 0.85


def _read_text(path: Path, offset: int = 0, limit: int | None = None) -> str:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if offset:
        lines = lines[offset:]
    if limit:
        lines = lines[:limit]
    return _clip("\n".join(f"{i + offset + 1}\t{l}" for i, l in enumerate(lines)))


def _read_csv(path: Path) -> str:
    out: List[str] = []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
        for i, row in enumerate(csv.reader(f, delimiter=delim)):
            out.append(" | ".join(row))
            if i >= 500:
                out.append("… [أكثر من 500 صف]")
                break
    return _clip("📊 " + path.name + " (جدول):\n" + "\n".join(out))


def _read_zip(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        head = [f"📦 أرشيف ZIP: {path.name} — {len(names)} عنصر\n"]
        for n in names[:200]:
            try:
                sz = z.getinfo(n).file_size
            except Exception:
                sz = 0
            head.append(f"  • {n} ({sz} بايت)")
        if len(names) > 200:
            head.append(f"  … و{len(names) - 200} عنصر آخر")
        # استخراج مضمّن لمحتوى الملفات النصية الصغيرة
        head.append("\n— محتوى الملفات النصية الصغيرة —")
        shown = 0
        for n in names:
            if n.endswith("/"):
                continue
            if Path(n).suffix.lower() in _TEXT_EXT:
                try:
                    data = z.read(n)
                    if len(data) <= 50_000 and _looks_text(data[:1024]):
                        head.append(f"\n### {n}\n" + data.decode("utf-8", "replace"))
                        shown += 1
                except Exception:
                    continue
            if shown >= 20:
                head.append("\n… [عدد الملفات النصية المعروضة بلغ الحد]")
                break
    return _clip("\n".join(head))


def _read_tar(path: Path) -> str:
    out = [f"📦 أرشيف TAR: {path.name}"]
    try:
        with tarfile.open(path) as t:
            members = t.getmembers()
            out.append(f"— {len(members)} عنصر")
            for m in members[:200]:
                kind = "📁" if m.isdir() else "📄"
                out.append(f"  {kind} {m.name} ({m.size} بايت)")
            if len(members) > 200:
                out.append(f"  … و{len(members) - 200} عنصر آخر")
    except Exception as e:
        out.append(f"تعذّر فتح الأرشيف: {e}")
    return _clip("\n".join(out))


def _xml_text(raw: bytes) -> str:
    """استخراج النص المرئي من XML (إزالة الوسوم)."""
    txt = raw.decode("utf-8", "replace")
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()


def _read_office(path: Path) -> str:
    """استخراج نصّ من مستندات Office (zip+XML) دون مكتبات خارجية."""
    ext = path.suffix.lower()
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            parts: List[str] = []
            if ext == ".docx":
                if "word/document.xml" in names:
                    parts.append(_xml_text(z.read("word/document.xml")))
            elif ext == ".pptx":
                slides = sorted(n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n))
                for i, n in enumerate(slides, 1):
                    parts.append(f"— شريحة {i} —\n" + _xml_text(z.read(n)))
            elif ext == ".xlsx":
                if "xl/sharedStrings.xml" in names:
                    parts.append(_xml_text(z.read("xl/sharedStrings.xml")))
                for n in sorted(x for x in names if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
                    parts.append(f"— ورقة: {n} —\n" + _xml_text(z.read(n))[:5000])
            else:  # OpenDocument (odt/ods/odp)
                if "content.xml" in names:
                    parts.append(_xml_text(z.read("content.xml")))
            body = "\n\n".join(p for p in parts if p) or "(لا نصّ مُستخرَج)"
            return _clip(f"📄 مستند {ext[1:].upper()}: {path.name}\n\n{body}")
    except Exception as e:
        return f"تعذّر استخراج نصّ المستند {path.name}: {e}"


def _read_binary(path: Path) -> str:
    data = path.read_bytes()[:512]
    hex_lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        asc = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        hex_lines.append(f"{i:04x}  {hex_part:<48}  {asc}")
    size = path.stat().st_size
    return (f"🔢 ملف ثنائي: {path.name} ({size} بايت)\n"
            f"   (ليس نصّاً ولا صورة/مستند مدعوم — معاينة hex لأول 512 بايت)\n\n"
            + "\n".join(hex_lines))


def read_any(path: str, offset: int = 0, limit: int | None = None) -> str:
    """قراءة ذكية لأي ملف → نصّ. تدعم نص/CSV/JSON/zip/tar/office/ثنائي.

    ملاحظة: الصور و PDF لا تُقرأ هنا — تُرسَل للنموذج الرؤيوي على مستوى الرسالة.
    """
    p = Path(path)
    if not p.exists():
        return f"الملف غير موجود: {path}"
    if p.is_dir():
        entries = sorted(p.iterdir())
        head = [f"📁 مجلد: {p} — {len(entries)} عنصر"]
        for e in entries[:300]:
            head.append(("  📁 " if e.is_dir() else "  📄 ") + e.name)
        return "\n".join(head)
    ext = p.suffix.lower()
    try:
        if ext in _OFFICE_ZIP:
            return _read_office(p)
        if ext == ".zip":
            return _read_zip(p)
        if ext in _ARCHIVE_TAR or ".tar." in p.name.lower():
            return _read_tar(p)
        if ext in (".csv", ".tsv"):
            return _read_csv(p)
        if ext in _TEXT_EXT:
            return _read_text(p, offset, limit)
        # مجهول الامتداد: خمّن حسب المحتوى
        sample = p.read_bytes()[:2048]
        if _looks_text(sample):
            return _read_text(p, offset, limit)
        # ربما أرشيف بلا امتداد صحيح
        if zipfile.is_zipfile(p):
            return _read_zip(p)
        if tarfile.is_tarfile(p):
            return _read_tar(p)
        return _read_binary(p)
    except Exception as e:
        return f"خطأ في قراءة {path}: {e}"


def extract_archive(path: str, dest: str) -> str:
    """فكّ ضغط أرشيف zip/tar إلى مجلد وجهة (حماية من مسارات الهروب)."""
    p = Path(path)
    d = Path(dest)
    if not p.exists():
        return f"الأرشيف غير موجود: {path}"
    d.mkdir(parents=True, exist_ok=True)
    droot = d.resolve()
    count = 0
    try:
        if zipfile.is_zipfile(p):
            with zipfile.ZipFile(p) as z:
                for m in z.namelist():
                    target = (d / m).resolve()
                    if not str(target).startswith(str(droot)):
                        continue  # تجاهُل مسار هروب (Zip Slip)
                    z.extract(m, d)
                    count += 1
        elif tarfile.is_tarfile(p):
            with tarfile.open(p) as t:
                for m in t.getmembers():
                    target = (d / m.name).resolve()
                    if not str(target).startswith(str(droot)):
                        continue
                    t.extract(m, d)
                    count += 1
        else:
            return f"ليس أرشيف zip/tar مدعوماً: {path}"
    except Exception as e:
        return f"تعذّر فكّ الأرشيف: {e}"
    return f"✅ فُكّ الأرشيف إلى {d} ({count} عنصر)"
