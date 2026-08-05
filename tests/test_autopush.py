"""
test_autopush.py — اختبارات الرفع التلقائي (core/autopush.py)
============================================================
يستخدم مستودعات git حقيقية مؤقتة (remote مجرّد + نسخة عمل) — بلا شبكة.
"""

import subprocess
from pathlib import Path

import pytest

from core import autopush


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    """نسخة عمل مرتبطة بـ remote مجرّد محلي (origin/main)."""
    bare = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run(["git", "init", "--bare", str(bare)], capture_output=True)
    subprocess.run(["git", "init", str(work)], capture_output=True)
    _git(work, "config", "user.email", "test@weaver.local")
    _git(work, "config", "user.name", "Weaver Test")
    _git(work, "checkout", "-b", "main")
    _git(work, "remote", "add", "origin", str(bare))
    # commit أولي حتى يوجد HEAD
    (work / "README.md").write_text("init\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")
    return work, bare


def _clean_env(monkeypatch):
    for k in ("WEAVER_AUTO_PUSH", "WEAVER_AUTO_PUSH_BRANCH", "WEAVER_AUTO_PUSH_REMOTE"):
        monkeypatch.delenv(k, raising=False)


def test_disabled_is_noop(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    res = autopush.auto_push(str(tmp_path))
    assert res["pushed"] is False and res["reason"] == "disabled"


def test_not_a_repo(tmp_path, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("WEAVER_AUTO_PUSH", "1")
    res = autopush.auto_push(str(tmp_path))
    assert res["pushed"] is False and res["reason"] == "not_a_repo"


def test_no_changes(repo, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("WEAVER_AUTO_PUSH", "1")
    work, _ = repo
    res = autopush.auto_push(str(work))
    assert res["pushed"] is False and res["reason"] == "no_changes"


def test_push_real_changes(repo, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("WEAVER_AUTO_PUSH", "1")
    work, bare = repo
    (work / "new.txt").write_text("hello\n", encoding="utf-8")
    msgs = []
    res = autopush.auto_push(str(work), task_summary="add new file",
                             notify=lambda l, m: msgs.append((l, m)))
    assert res["pushed"] is True and res["files"] == 1
    # الرسالة الوصفية استُخدمت في الـ commit
    log = _git(work, "log", "-1", "--pretty=%s").stdout.strip()
    assert log == "🕸️ WeaverCode: add new file"
    # وصلت فعلاً إلى الـ remote المجرّد (فرع main تحديداً)
    remote_log = _git(bare, "log", "-1", "--pretty=%s", "main").stdout.strip()
    assert "add new file" in remote_log
    assert any(l == "success" for l, _ in msgs)


def test_force_bypasses_disable(repo, monkeypatch):
    _clean_env(monkeypatch)   # WEAVER_AUTO_PUSH غير مضبوط (معطّل)
    work, _ = repo
    (work / "f.txt").write_text("x\n", encoding="utf-8")
    res = autopush.auto_push(str(work), force=True)
    assert res["pushed"] is True


def test_custom_remote_and_branch(repo, monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("WEAVER_AUTO_PUSH", "1")
    monkeypatch.setenv("WEAVER_AUTO_PUSH_REMOTE", "origin")
    monkeypatch.setenv("WEAVER_AUTO_PUSH_BRANCH", "main")
    work, bare = repo
    (work / "g.txt").write_text("y\n", encoding="utf-8")
    res = autopush.auto_push(str(work))
    assert res["pushed"] is True and res["message"] == "origin/main"


def test_commit_message_variants():
    assert autopush._commit_message("do X", ["a"]) == "🕸️ WeaverCode: do X"
    assert autopush._commit_message("", ["only.py"]) == "🕸️ WeaverCode: update only.py"
    assert autopush._commit_message("", ["a", "b"]) == "🕸️ WeaverCode: update a, b"
    assert autopush._commit_message("", [f"f{i}" for i in range(9)]).endswith("9 files")


def test_never_raises_on_bad_workdir(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("WEAVER_AUTO_PUSH", "1")
    # مجلد غير موجود إطلاقاً — يجب ألا يرمي استثناء
    res = autopush.auto_push("/nonexistent/path/xyz")
    assert res["pushed"] is False


def test_weaver_wrapper_delegates(repo, monkeypatch):
    """weaver._maybe_auto_push يفوّض لـ core.autopush ويحترم التفعيل."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("WEAVER_AUTO_PUSH", "1")
    work, bare = repo
    (work / "w.txt").write_text("z\n", encoding="utf-8")
    import weaver
    weaver._maybe_auto_push(str(work), task_summary="via wrapper")
    remote_log = _git(bare, "log", "-1", "--pretty=%s", "main").stdout.strip()
    assert "via wrapper" in remote_log
