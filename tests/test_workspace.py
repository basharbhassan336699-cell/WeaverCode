"""
اختبارات مساحة عمل المستودع: استنساخ المستودع المختار محلياً ليعمل الوكيل عليه
(يعالج «فتحت مستودعاً ولم يفعل شيئاً» — كان الاختيار تجميلياً بلا استنساخ).
"""

import json
import os
import subprocess

import pytest


def _make_remote(tmp_path):
    """ينشئ مستودع git محلي يصلح كـ 'remote' للاستنساخ."""
    remote = tmp_path / "remote"
    remote.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(remote)], check=True)
    (remote / "README.md").write_text("# hello")
    subprocess.run(["git", "-C", str(remote), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(remote), "-c", "user.email=a@b.c",
                    "-c", "user.name=x", "commit", "-q", "-m", "init"], check=True)
    return remote


def _server(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "WEAVER_ROOT", tmp_path)
    (tmp_path / "config").mkdir(exist_ok=True)
    monkeypatch.setattr(server, "_WORKSPACE_FILE", tmp_path / "config" / "workspace.json")
    monkeypatch.setattr(server, "_workspaces_dir", lambda: tmp_path / "ws")
    monkeypatch.setattr(server, "_github_token", lambda: "")
    return server


def test_select_repo_clones_locally(tmp_path, monkeypatch):
    server = _server(tmp_path, monkeypatch)
    remote = _make_remote(tmp_path)
    r = server._api_github_select_repo({
        "full_name": "me/proj", "clone_url": str(remote), "default_branch": "main"})
    assert r["ok"] is True
    assert r["files"] >= 1
    ws = server._active_workspace()
    assert ws["repo"] == "me/proj"
    assert os.path.isfile(os.path.join(ws["work_dir"], "README.md"))


def test_select_repo_missing_data(tmp_path, monkeypatch):
    server = _server(tmp_path, monkeypatch)
    r = server._api_github_select_repo({"full_name": "", "clone_url": ""})
    assert r["ok"] is False


def test_workspace_clear(tmp_path, monkeypatch):
    server = _server(tmp_path, monkeypatch)
    remote = _make_remote(tmp_path)
    server._api_github_select_repo({
        "full_name": "me/proj", "clone_url": str(remote), "default_branch": "main"})
    assert server._active_workspace() != {}
    server._api_workspace_clear()
    assert server._active_workspace() == {}


def test_workspace_get_reports_active(tmp_path, monkeypatch):
    server = _server(tmp_path, monkeypatch)
    remote = _make_remote(tmp_path)
    server._api_github_select_repo({
        "full_name": "me/proj", "clone_url": str(remote), "default_branch": "main"})
    g = server._api_workspace_get()
    assert g["active"] is True and g["repo"] == "me/proj"


def test_reselect_updates_existing(tmp_path, monkeypatch):
    """إعادة اختيار نفس المستودع تُحدّثه (pull) لا تفشل."""
    server = _server(tmp_path, monkeypatch)
    remote = _make_remote(tmp_path)
    server._api_github_select_repo({
        "full_name": "me/proj", "clone_url": str(remote), "default_branch": "main"})
    r2 = server._api_github_select_repo({
        "full_name": "me/proj", "clone_url": str(remote), "default_branch": "main"})
    assert r2["ok"] is True
    assert r2["action"] == "تحديث"


def test_files_follow_active_workspace(tmp_path, monkeypatch):
    """الملفات المعروضة/القابلة للتنزيل = مساحة العمل النشِطة (لا OUTPUTS الثابت)."""
    server = _server(tmp_path, monkeypatch)
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)
    (clone / ".git" / "config").write_text("secret")
    (clone / "src").mkdir()
    (clone / "src" / "main.py").write_text("print(1)")
    (clone / "report.md").write_text("# r")
    (tmp_path / "config" / "workspace.json").write_text(
        json.dumps({"repo": "me/p", "work_dir": str(clone), "branch": "main"}))
    r = server._api_files()
    paths = sorted(f["path"] for f in r["files"])
    assert paths == ["report.md", "src/main.py"]  # .git مُتخطّى
    assert r["repo"] == "me/p"


def test_download_path_within_workspace(tmp_path, monkeypatch):
    server = _server(tmp_path, monkeypatch)
    clone = tmp_path / "clone"
    (clone / "src").mkdir(parents=True)
    (clone / "src" / "a.py").write_text("x")
    (tmp_path / "config" / "workspace.json").write_text(
        json.dumps({"repo": "me/p", "work_dir": str(clone), "branch": "main"}))
    ok = server._safe_output_path("src/a.py")
    assert ok is not None and os.path.isfile(ok)
    assert server._safe_output_path("../../etc/passwd") is None


def test_files_fallback_to_outputs_without_workspace(tmp_path, monkeypatch):
    server = _server(tmp_path, monkeypatch)
    # لا مساحة عمل → يعود لمجلد المخرجات
    out = tmp_path / "outs"
    out.mkdir()
    monkeypatch.setattr(server, "OUTPUTS", out)
    (out / "deliver.txt").write_text("done")
    r = server._api_files()
    assert any(f["name"] == "deliver.txt" for f in r["files"])
    assert r["repo"] == ""


def test_daemon_uses_workspace_as_workdir(tmp_path, monkeypatch):
    import background.daemon as daemon
    (tmp_path / "config").mkdir()
    (tmp_path / "background").mkdir()
    repo = tmp_path / "clone"
    repo.mkdir()
    (tmp_path / "config" / "workspace.json").write_text(
        json.dumps({"repo": "me/x", "work_dir": str(repo), "branch": "main"}))
    monkeypatch.setattr(daemon, "__file__", str(tmp_path / "background" / "daemon.py"))
    assert daemon._active_work_dir() == str(repo)
