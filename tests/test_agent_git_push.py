"""
اختبار قدرة الوكيل على البناء في المستودع المتصل والرفع إلى GitHub ذاتياً
(كـ Claude Code): GitCommit + GitPush على مساحة العمل النشِطة مع مصادقة التوكن.
"""

import os
import subprocess
import tempfile

from core.tools.registry import ToolRegistry


def _make_repo():
    base = tempfile.mkdtemp()
    remote = base + "/remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", remote],
                   check=True, capture_output=True)
    clone = base + "/clone"
    subprocess.run(["git", "clone", remote, clone], capture_output=True)
    subprocess.run(["git", "-C", clone, "checkout", "-b", "main"], capture_output=True)
    subprocess.run(["git", "-C", clone, "config", "user.email", "a@b.c"])
    subprocess.run(["git", "-C", clone, "config", "user.name", "x"])
    open(clone + "/README.md", "w").write("# init")
    subprocess.run(["git", "-C", clone, "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", clone, "commit", "-qm", "init"], capture_output=True)
    return base, remote, clone


def test_agent_builds_and_pushes(monkeypatch):
    base, remote, clone = _make_repo()
    reg = ToolRegistry(work_dir=clone)
    monkeypatch.setattr(reg, "_active_workspace",
                        lambda: {"work_dir": clone, "branch": "main", "clone_url": remote})
    monkeypatch.setattr(reg, "_github_token", lambda: "")

    # الوكيل يبني ملفاً في المستودع
    open(clone + "/app.py", "w").write("print('hi')")
    commit_out = reg._git_commit("add app.py")
    assert "app.py" in commit_out or "file" in commit_out.lower()

    # ثم يرفعه إلى GitHub (remote)
    reg._git_push()
    check = base + "/check"
    subprocess.run(["git", "clone", "-q", remote, check], capture_output=True)
    assert os.path.isfile(check + "/app.py")


def test_push_masks_token(monkeypatch):
    base, remote, clone = _make_repo()
    reg = ToolRegistry(work_dir=clone)
    monkeypatch.setattr(reg, "_active_workspace",
                        lambda: {"work_dir": clone, "branch": "main",
                                 "clone_url": "https://github.com/me/x.git"})
    monkeypatch.setattr(reg, "_github_token", lambda: "ghp_SECRET123")
    out = reg._git_push()  # سيفشل (remote وهمي) لكن يجب ألا يسرّب التوكن
    assert "ghp_SECRET123" not in out


def test_git_commit_defaults_to_workspace(monkeypatch):
    base, remote, clone = _make_repo()
    reg = ToolRegistry(work_dir="/tmp")
    monkeypatch.setattr(reg, "_active_workspace",
                        lambda: {"work_dir": clone, "branch": "main", "clone_url": remote})
    open(clone + "/x.txt", "w").write("data")
    out = reg._git_commit("add x")
    assert "x.txt" in out or "file" in out.lower()
