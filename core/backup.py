"""
backup.py — نسخ احتياطي وتصدير للذاكرة والجلسات في WeaverCode 🕸️
================================================================
Backup / export of the persistent memory (conversations, facts) and the
saved sessions. stdlib-only (sqlite3 + tarfile + json), so it runs on
Termux/Windows/macOS/Linux with no extra dependencies.

A backup is a portable ``.tar.gz`` bundle containing:
  • ``memory.db``    — a consistent copy of the SQLite database
  • ``export.json``  — a version-independent JSON dump of every table
  • ``manifest.json``— metadata (counts, timestamp, WeaverCode version)

The database is never touched during a backup; restore always snapshots the
current database first, so no data is lost by mistake.
"""
from __future__ import annotations

import io
import json
import os
import sqlite3
import tarfile
import time
from pathlib import Path
from typing import Dict, List, Optional

# الجداول التي نصدّرها (المحادثات + الحقائق + الأنماط + الجلسات)
_TABLES = ("conversations", "facts", "patterns", "sessions")


def _db_path(db_path: Optional[str] = None) -> Path:
    """مسار قاعدة الذاكرة، مع توسيع ~ (يطابق ما يستخدمه MemoryStore)."""
    raw = db_path or os.environ.get(
        "WEAVER_DB_PATH", str(Path.home() / ".weaver" / "memory.db"))
    return Path(os.path.expanduser(raw))


def _backup_dir() -> Path:
    """مجلد النسخ الاحتياطية الافتراضي (~/.weaver/backup)."""
    d = Path.home() / ".weaver" / "backup"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _weaver_version() -> str:
    try:
        from core.ui import WEAVER_VERSION
        return WEAVER_VERSION
    except Exception:
        return "unknown"


def export_json(db_path: Optional[str] = None) -> Dict:
    """يصدّر كل الجداول إلى قاموس محمول (قابل للحفظ كـ JSON).

    آمن حتى لو غابت بعض الجداول (يتجاهلها بهدوء)."""
    db = _db_path(db_path)
    data: Dict[str, object] = {
        "weavercode_export": 1,
        "version": _weaver_version(),
        "exported_at": time.time(),
        "db": str(db),
    }
    for tbl in _TABLES:
        data[tbl] = []
    if not db.exists():
        return data
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    try:
        for tbl in _TABLES:
            try:
                rows = conn.execute(f"SELECT * FROM {tbl}").fetchall()
                data[tbl] = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                # الجدول غير موجود في قواعد أقدم — نتجاوزه
                pass
    finally:
        conn.close()
    return data


def _counts(export: Dict) -> Dict[str, int]:
    return {tbl: len(export.get(tbl, []) or []) for tbl in _TABLES}


def _add_bytes(tar: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(payload)
    info.mtime = int(time.time())
    tar.addfile(info, io.BytesIO(payload))


def create_backup(dest: Optional[str] = None,
                  db_path: Optional[str] = None) -> Path:
    """ينشئ نسخة احتياطية (.tar.gz) للذاكرة والجلسات ويُرجع مسار الملف.

    dest: مسار ملف أو مجلد (اختياري). الافتراضي: ~/.weaver/backup/.
    قاعدة البيانات تُنسَخ نسخةً متّسقة عبر واجهة sqlite backup (لا نسخ ملف حيّ)."""
    db = _db_path(db_path)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    default_name = f"weaver-backup-{stamp}.tar.gz"
    if dest:
        out = Path(os.path.expanduser(dest))
        if out.is_dir() or dest.endswith(("/", os.sep)):
            out = out / default_name
    else:
        out = _backup_dir() / default_name
    out.parent.mkdir(parents=True, exist_ok=True)
    # تفادي الكتابة فوق نسخة أُنشئت في الثانية نفسها (دقّة الطابع = ثانية)
    if out.exists():
        stem = out.name[:-len(".tar.gz")] if out.name.endswith(".tar.gz") else out.stem
        i = 2
        while out.exists():
            out = out.parent / f"{stem}-{i}.tar.gz"
            i += 1

    export = export_json(db)
    manifest = {
        "weavercode_backup": 1,
        "version": _weaver_version(),
        "created_at": time.time(),
        "created_at_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_db": str(db),
        "counts": _counts(export),
    }

    tmp_db = out.parent / f".mem-snapshot-{stamp}.db"
    try:
        if db.exists():
            src = sqlite3.connect(str(db))
            dst = sqlite3.connect(str(tmp_db))
            try:
                with dst:
                    src.backup(dst)   # نسخة متّسقة حتى أثناء الكتابة
            finally:
                src.close()
                dst.close()
        with tarfile.open(out, "w:gz") as tar:
            if tmp_db.exists():
                tar.add(str(tmp_db), arcname="memory.db")
            _add_bytes(tar, "export.json",
                       json.dumps(export, ensure_ascii=False, indent=2).encode("utf-8"))
            _add_bytes(tar, "manifest.json",
                       json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    finally:
        if tmp_db.exists():
            try:
                tmp_db.unlink()
            except Exception:
                pass
    return out


def list_backups() -> List[Dict]:
    """قائمة النسخ الاحتياطية في المجلد الافتراضي (الأحدث أولاً)."""
    d = _backup_dir()
    out = []
    for f in sorted(d.glob("weaver-backup-*.tar.gz"),
                    key=lambda p: p.stat().st_mtime, reverse=True):
        info: Dict[str, object] = {
            "path": str(f), "name": f.name,
            "size": f.stat().st_size, "mtime": f.stat().st_mtime}
        try:
            with tarfile.open(f, "r:gz") as tar:
                m = tar.extractfile("manifest.json")
                if m:
                    info["manifest"] = json.loads(m.read().decode("utf-8"))
        except Exception:
            pass
        out.append(info)
    return out


def prune_backups(keep: int) -> List[str]:
    """يحذف أقدم النسخ في المجلد الافتراضي مبقياً أحدث ``keep`` منها.

    يُرجع مسارات النسخ المحذوفة. keep<=0 لا يحذف شيئاً (حماية)."""
    if keep is None or keep <= 0:
        return []
    items = list_backups()   # الأحدث أولاً
    removed: List[str] = []
    for it in items[keep:]:
        try:
            Path(it["path"]).unlink()
            removed.append(it["path"])
        except Exception:
            pass
    return removed


def restore_backup(archive: str, db_path: Optional[str] = None,
                   overwrite: bool = False) -> str:
    """يستعيد قاعدة الذاكرة من نسخة احتياطية.

    يحفظ نسخةً من قاعدة البيانات الحالية أولاً (‏.pre-restore) فلا تُفقد بيانات.
    overwrite=False يمنع الكتابة فوق قاعدة موجودة ما لم يُطلب صراحةً."""
    src = Path(os.path.expanduser(archive))
    if not src.exists():
        return f"النسخة الاحتياطية غير موجودة: {archive}"
    db = _db_path(db_path)
    if db.exists() and not overwrite:
        return ("قاعدة الذاكرة موجودة بالفعل. مرّر overwrite=True للكتابة فوقها "
                "(سيُحفظ نسخ احتياطي تلقائي منها أولاً).")
    db.parent.mkdir(parents=True, exist_ok=True)

    # احتفظ بنسخة من الحالية قبل أي استبدال
    if db.exists():
        safety = db.with_suffix(
            db.suffix + f".pre-restore-{time.strftime('%Y%m%d-%H%M%S')}")
        try:
            import shutil
            shutil.copy2(str(db), str(safety))
        except Exception:
            safety = None
    else:
        safety = None

    try:
        with tarfile.open(src, "r:gz") as tar:
            names = tar.getnames()
            if "memory.db" in names:
                member = tar.getmember("memory.db")
                extracted = tar.extractfile(member)
                if extracted is None:
                    return "تعذّر قراءة memory.db من النسخة الاحتياطية."
                db.write_bytes(extracted.read())
            elif "export.json" in names:
                # لا قاعدة بيانات — أعِد البناء من التصدير JSON
                exp = tar.extractfile("export.json")
                if exp is None:
                    return "النسخة الاحتياطية لا تحوي بيانات قابلة للاستعادة."
                _import_export(json.loads(exp.read().decode("utf-8")), db)
            else:
                return "النسخة الاحتياطية غير صالحة (لا memory.db ولا export.json)."
    except tarfile.TarError as e:
        return f"النسخة الاحتياطية تالفة: {e}"

    msg = f"✅ استُعيدت الذاكرة من {src.name} إلى {db}"
    if safety:
        msg += f"\n(نُسخت القاعدة السابقة إلى {Path(safety).name})"
    return msg


def _import_export(export: Dict, db: Path) -> None:
    """يعيد بناء قاعدة الذاكرة من تصدير JSON (احتياطي عند غياب memory.db)."""
    # نستعين بـ MemoryStore ليُنشئ المخطّط الكامل + الفهارس
    from core.memory.store import MemoryStore
    store = MemoryStore(str(db))   # ينشئ الجداول والـ FTS
    conn = sqlite3.connect(str(db))
    try:
        for row in export.get("conversations", []) or []:
            conn.execute(
                """INSERT INTO conversations
                   (session_id, prompt, response, tools_used, created_at, importance)
                   VALUES (?,?,?,?,?,?)""",
                (row.get("session_id", ""), row.get("prompt", ""),
                 row.get("response", ""), row.get("tools_used", "[]"),
                 row.get("created_at", time.time()), row.get("importance", 1.0)))
        for row in export.get("facts", []) or []:
            conn.execute(
                """INSERT OR REPLACE INTO facts
                   (key, value, tags, created_at, updated_at, access_count)
                   VALUES (?,?,?,?,?,?)""",
                (row.get("key"), row.get("value"), row.get("tags", "[]"),
                 row.get("created_at", time.time()),
                 row.get("updated_at", time.time()), row.get("access_count", 0)))
        store._ensure_sessions_table(conn)
        for row in export.get("sessions", []) or []:
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                   (id, name, last_prompt, messages_json, created_at, updated_at)
                   VALUES (?,?,?,?,?,?)""",
                (row.get("id"), row.get("name"), row.get("last_prompt"),
                 row.get("messages_json", "[]"),
                 row.get("created_at", time.time()),
                 row.get("updated_at", time.time())))
        conn.commit()
    finally:
        conn.close()
