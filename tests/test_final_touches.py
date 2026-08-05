"""
test_final_touches.py — اختبارات اللمسات الأخيرة
================================================
5) ARCHITECTURE.md + CONTRIBUTING.md موجودان وغير فارغين
6) نسخ احتياطي/تصدير للذاكرة والجلسات (core/backup.py)
7) فهرسة رموز الكود (core/index/symbols.py) + أداة SymbolIndex
"""

import asyncio
import json
import time
from pathlib import Path

import pytest

from core import backup as bk
from core.index import symbols as sym
from core.memory.store import MemoryStore
from core.tools.registry import ToolRegistry

ROOT = Path(__file__).resolve().parent.parent


# ── 5) وثائق المستودع العام ───────────────────────────────────────────────────

@pytest.mark.parametrize("name", ["ARCHITECTURE.md", "CONTRIBUTING.md"])
def test_repo_docs_exist(name):
    p = ROOT / name
    assert p.exists(), f"{name} مفقود"
    assert len(p.read_text(encoding="utf-8").strip()) > 400, f"{name} قصير جداً"


# ── 6) النسخ الاحتياطي والتصدير ───────────────────────────────────────────────

def _seed(db: str) -> None:
    store = MemoryStore(db)
    asyncio.run(store.save("q?", "a!", ["Read"], "sess-1"))
    store.save_fact("proj", "WeaverCode", ["meta"])
    store.save_session("sess-1", "Session One", "q?",
                       json.dumps([{"role": "user", "content": "hi"}]))


def test_export_json_collects_all_tables(tmp_path):
    db = str(tmp_path / "m.db")
    _seed(db)
    exp = bk.export_json(db)
    assert exp["weavercode_export"] == 1
    assert len(exp["conversations"]) == 1
    assert len(exp["facts"]) == 1
    assert len(exp["sessions"]) == 1


def test_export_json_missing_db_is_safe(tmp_path):
    exp = bk.export_json(str(tmp_path / "nope.db"))
    assert exp["conversations"] == [] and exp["sessions"] == []


def test_backup_and_restore_round_trip(tmp_path):
    db = str(tmp_path / "m.db")
    _seed(db)
    out = bk.create_backup(dest=str(tmp_path), db_path=db)
    assert out.exists() and out.suffix == ".gz"

    # الأرشيف يحوي القطع الثلاث
    import tarfile
    with tarfile.open(out, "r:gz") as tar:
        names = set(tar.getnames())
    assert {"memory.db", "export.json", "manifest.json"} <= names

    # استعادة إلى قاعدة جديدة
    new_db = str(tmp_path / "restored.db")
    msg = bk.restore_backup(str(out), db_path=new_db, overwrite=True)
    assert msg.startswith("✅")
    st = MemoryStore(new_db).get_stats()
    assert st["conversations"] == 1 and st["facts"] == 1


def test_restore_refuses_existing_without_overwrite(tmp_path):
    db = str(tmp_path / "m.db")
    _seed(db)
    out = bk.create_backup(dest=str(tmp_path), db_path=db)
    msg = bk.restore_backup(str(out), db_path=db, overwrite=False)
    assert "overwrite" in msg.lower()


def test_restore_missing_archive(tmp_path):
    msg = bk.restore_backup(str(tmp_path / "ghost.tar.gz"),
                            db_path=str(tmp_path / "x.db"))
    assert "غير موجود" in msg


def test_restore_from_export_only_backup(tmp_path):
    # نسخة احتياطية بلا memory.db (export.json فقط) تُعاد بناؤها
    db = str(tmp_path / "m.db")
    _seed(db)
    exp = bk.export_json(db)
    import tarfile, io
    arc = tmp_path / "export-only.tar.gz"
    payload = json.dumps(exp, ensure_ascii=False).encode("utf-8")
    with tarfile.open(arc, "w:gz") as tar:
        info = tarfile.TarInfo("export.json")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))
    new_db = str(tmp_path / "rebuilt.db")
    msg = bk.restore_backup(str(arc), db_path=new_db, overwrite=True)
    assert msg.startswith("✅")
    assert MemoryStore(new_db).get_stats()["conversations"] == 1


# ── 7) فهرسة الرموز ───────────────────────────────────────────────────────────

def test_python_symbols_extracted(tmp_path):
    f = tmp_path / "mod.py"
    f.write_text(
        "def top(a, b):\n    return a\n\n"
        "class Foo:\n    def method(self, x):\n        return x\n",
        encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)
    names = {s["name"]: s["kind"] for s in idx["symbols"]}
    assert names.get("top") == "function"
    assert names.get("Foo") == "class"
    assert names.get("method") == "method"


def test_js_symbols_extracted(tmp_path):
    f = tmp_path / "app.js"
    f.write_text(
        "export function doThing() {}\n"
        "class Widget {}\n"
        "const handler = async (e) => {}\n",
        encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)
    names = {s["name"] for s in idx["symbols"]}
    assert {"doThing", "Widget", "handler"} <= names


def test_find_exact_before_partial(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("def run():\n    pass\ndef runner():\n    pass\n", encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)
    res = sym.find(idx, "run")
    assert res[0]["name"] == "run"        # المطابقة الدقيقة أولاً
    assert any(s["name"] == "runner" for s in res)


def test_index_skips_noise_dirs(tmp_path):
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("function hidden(){}", encoding="utf-8")
    (tmp_path / "keep.py").write_text("def kept():\n    pass\n", encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)
    names = {s["name"] for s in idx["symbols"]}
    assert "kept" in names and "hidden" not in names


def test_syntax_error_file_is_tolerated(tmp_path):
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("def fine():\n    pass\n", encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)  # لا يرمي استثناء
    assert any(s["name"] == "fine" for s in idx["symbols"])


def test_symbol_index_tool(tmp_path):
    (tmp_path / "s.py").write_text("def alpha():\n    pass\n", encoding="utf-8")
    reg = ToolRegistry(work_dir=str(tmp_path))
    built = asyncio.run(reg.execute("SymbolIndex", {"action": "build"}))
    assert "✅" in built
    found = asyncio.run(reg.execute("SymbolIndex", {"action": "find", "name": "alpha"}))
    assert "s.py" in found and "alpha" in found
    outline = asyncio.run(reg.execute("SymbolIndex", {"action": "outline", "file": "s.py"}))
    assert "alpha" in outline


# ── 7b) لغات إضافية في الفهرس (Go/Rust/Java) ─────────────────────────────────

def test_go_symbols(tmp_path):
    (tmp_path / "m.go").write_text(
        "package m\n"
        "func Handle(w http.ResponseWriter) {}\n"
        "func (s *Server) Serve() {}\n"
        "type Server struct {}\n"
        "type Reader interface {}\n", encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)
    kinds = {s["name"]: s["kind"] for s in idx["symbols"]}
    assert kinds.get("Handle") == "function"
    assert kinds.get("Serve") == "function"      # method with receiver
    assert kinds.get("Server") == "struct"
    assert kinds.get("Reader") == "interface"


def test_rust_symbols(tmp_path):
    (tmp_path / "m.rs").write_text(
        "pub fn run() {}\n"
        "async fn fetch() {}\n"
        "pub struct Config {}\n"
        "enum State {}\n"
        "trait Draw {}\n", encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)
    kinds = {s["name"]: s["kind"] for s in idx["symbols"]}
    assert kinds.get("run") == "function"
    assert kinds.get("fetch") == "function"
    assert kinds.get("Config") == "struct"
    assert kinds.get("State") == "enum"
    assert kinds.get("Draw") == "trait"


def test_java_symbols(tmp_path):
    (tmp_path / "M.java").write_text(
        "public class Widget {\n"
        "    public void render(int x) {\n"
        "        return;\n"
        "    }\n"
        "}\n"
        "interface Clickable {}\n", encoding="utf-8")
    idx = sym.build_index(str(tmp_path), cache=False)
    kinds = {s["name"]: s["kind"] for s in idx["symbols"]}
    assert kinds.get("Widget") == "class"
    assert kinds.get("Clickable") == "interface"
    assert kinds.get("render") == "method"


# ── 7c) البناء التزايدي (incremental) ────────────────────────────────────────

def test_incremental_reuses_unchanged_and_reparses_changed(tmp_path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("def one():\n    pass\n", encoding="utf-8")
    b.write_text("def two():\n    pass\n", encoding="utf-8")
    first = sym.build_index(str(tmp_path), cache=True)
    assert first["count"] == 2 and first["reused_files"] == 0

    # عدّل a فقط (اضبط mtime للأمام لضمان الاختلاف)
    import os as _os
    a.write_text("def one():\n    pass\ndef one_more():\n    pass\n", encoding="utf-8")
    future = time.time() + 10
    _os.utime(a, (future, future))

    second = sym.build_index(str(tmp_path), cache=True, incremental=True)
    names = {s["name"] for s in second["symbols"]}
    assert {"one", "one_more", "two"} <= names   # a أُعيد تحليله
    assert second["reused_files"] == 1           # b أُعيد استخدامه دون تحليل


def test_incremental_drops_deleted_files(tmp_path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("def keep():\n    pass\n", encoding="utf-8")
    b.write_text("def gone():\n    pass\n", encoding="utf-8")
    sym.build_index(str(tmp_path), cache=True)
    b.unlink()
    idx = sym.build_index(str(tmp_path), cache=True, incremental=True)
    names = {s["name"] for s in idx["symbols"]}
    assert "keep" in names and "gone" not in names


def test_incremental_falls_back_to_full_without_cache(tmp_path):
    (tmp_path / "x.py").write_text("def solo():\n    pass\n", encoding="utf-8")
    # لا كاش سابق → بناء كامل دون خطأ
    idx = sym.build_index(str(tmp_path), cache=False, incremental=True)
    assert any(s["name"] == "solo" for s in idx["symbols"])


# ── 6b) تقليم النسخ الاحتياطية (--keep) ──────────────────────────────────────

def test_prune_backups_keeps_newest(tmp_path, monkeypatch):
    # وجّه مجلد النسخ الافتراضي إلى مجلد مؤقت
    bkdir = tmp_path / "backups"
    bkdir.mkdir()
    monkeypatch.setattr(bk, "_backup_dir", lambda: bkdir)
    db = str(tmp_path / "m.db")
    _seed(db)
    outs = []
    for _ in range(4):
        outs.append(bk.create_backup(db_path=db))   # تُكتب في bkdir
    assert len(bk.list_backups()) == 4
    removed = bk.prune_backups(keep=2)
    assert len(removed) == 2
    assert len(bk.list_backups()) == 2


def test_prune_backups_zero_keep_is_noop(tmp_path, monkeypatch):
    bkdir = tmp_path / "backups"
    bkdir.mkdir()
    monkeypatch.setattr(bk, "_backup_dir", lambda: bkdir)
    db = str(tmp_path / "m.db")
    _seed(db)
    bk.create_backup(db_path=db)
    assert bk.prune_backups(0) == []
    assert len(bk.list_backups()) == 1
