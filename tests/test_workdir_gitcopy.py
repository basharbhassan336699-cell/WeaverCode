"""
اختبارات: عدم نسخ ملفات المستودع لـ Downloads (تُدار بـ GitPush)، وتمرير
work_dir لمجلد المستودع، والرفع التلقائي الاختياري.
"""

import os
import subprocess
import tempfile

import pytest


def _engine_stub(work_dir, created):
    import core.engine.query_engine as qe

    class _Tools:
        pass
    t = _Tools()
    t.work_dir = work_dir
    t._created_files = list(created)
    e = object.__new__(qe.QueryEngine)
    e.tools = t
    return e


def test_git_files_not_copied_to_downloads(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    fg = repo / "a.py"
    fg.write_text("x")
    plain = tmp_path / "plain"
    plain.mkdir()
    fp = plain / "b.py"
    fp.write_text("y")
    downloads = tmp_path / "dl"
    downloads.mkdir()

    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: str(downloads) if p == "~/storage/downloads"
                        else os.path.expanduser(p))
    e = _engine_stub(str(repo), [str(fg), str(fp)])
    e._copy_created_to_downloads()
    assert not (downloads / "a.py").exists()   # ملف git → GitPush يتولّاه
    assert (downloads / "b.py").exists()        # ملف عادي → نُسِخ


def test_created_files_cleared_after(tmp_path, monkeypatch):
    plain = tmp_path / "p"
    plain.mkdir()
    f = plain / "c.py"
    f.write_text("z")
    downloads = tmp_path / "dl"
    downloads.mkdir()
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: str(downloads) if p == "~/storage/downloads"
                        else os.path.expanduser(p))
    e = _engine_stub(str(plain), [str(f)])
    e._copy_created_to_downloads()
    assert e.tools._created_files == []


def test_auto_push_disabled_by_default(tmp_path, monkeypatch):
    import weaver
    monkeypatch.delenv("WEAVER_AUTO_PUSH", raising=False)
    called = {"push": False}
    real_run = subprocess.run

    def spy(cmd, *a, **k):
        if cmd and cmd[:2] == ["git", "push"]:
            called["push"] = True
        return real_run(cmd, *a, **k)

    monkeypatch.setattr(weaver.subprocess if hasattr(weaver, "subprocess") else subprocess,
                        "run", spy, raising=False)
    weaver._maybe_auto_push(str(tmp_path))
    assert called["push"] is False


def test_auto_push_skips_non_git(tmp_path, monkeypatch):
    """WEAVER_AUTO_PUSH=1 لكن المجلد ليس مستودع git → لا يُنفَّذ push."""
    import weaver
    monkeypatch.setenv("WEAVER_AUTO_PUSH", "1")
    # tmp_path ليس مستودع git → _maybe_auto_push يخرج بأمان بلا استثناء
    weaver._maybe_auto_push(str(tmp_path))  # يجب ألا يرمي


def test_build_engine_reads_work_dir_env(monkeypatch, tmp_path):
    """WEAVER_WORK_DIR يُضبَط كمجلد عمل الأدوات."""
    import weaver
    import asyncio
    monkeypatch.setenv("WEAVER_WORK_DIR", str(tmp_path))
    monkeypatch.setenv("WEAVER_API_KEY", "x")
    monkeypatch.setenv("WEAVER_BASE_URL", "https://x/v1")
    monkeypatch.setenv("WEAVER_MODEL", "m")

    async def _run():
        engine, provider, mcp = await weaver.build_engine("main")
        try:
            return engine.tools.work_dir
        finally:
            await mcp.stop_all()

    wd = asyncio.run(_run())
    assert os.path.abspath(wd) == os.path.abspath(str(tmp_path))
