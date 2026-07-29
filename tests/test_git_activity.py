"""
اختبارات شريط نشاط Git/GitHub:
- صحة جمع بيانات commits محلياً (+/-، الفرع، الرسالة).
- التعامل الآمن مع غياب GITHUB_TOKEN.
- صحة endpoint النشاط + الترقيم (Show N more).
- معاينة commit معلّق في وضع التخطيط.
"""

import os
import subprocess

import pytest


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("WEAVER_DB_PATH", str(tmp_path / "memory.db"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("WEAVER_GITHUB_TOKEN", raising=False)
    d = tmp_path / "repo"
    d.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(d)], check=True)
    subprocess.run(["git", "-C", str(d), "config", "user.email", "a@b.c"])
    subprocess.run(["git", "-C", str(d), "config", "user.name", "x"])
    return str(d)


def _commit(d, fname, content, msg):
    (open(os.path.join(d, fname), "w")).write(content)
    subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", d, "commit", "-qm", msg], capture_output=True)


# ── جمع commits محلياً ───────────────────────────────────────────────────────

def test_collect_commits_local(repo):
    from core import git_activity as ga
    _commit(repo, "a.py", "x=1\ny=2\nz=3\n", "add a")
    _commit(repo, "a.py", "x=1\n", "trim a")
    commits = ga.collect_commits(repo)
    assert len(commits) == 2
    assert commits[0]["message"] == "trim a"      # الأحدث أولاً
    assert commits[0]["removed"] == 2 and commits[0]["added"] == 0
    assert commits[1]["added"] == 3
    assert commits[0]["branch"] == "main"
    assert commits[0]["kind"] == "commit"


def test_collect_commits_non_git(tmp_path):
    from core import git_activity as ga
    assert ga.collect_commits(str(tmp_path)) == []
    assert ga.is_git_repo(str(tmp_path)) is False


# ── الأمان بلا توكن ──────────────────────────────────────────────────────────

def test_github_token_absent_safe(repo, monkeypatch):
    from core import git_activity as ga
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert ga.github_token() == "" or isinstance(ga.github_token(), str)


def test_collect_prs_without_token_or_slug(repo, monkeypatch):
    from core import git_activity as ga
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert ga.collect_pull_requests("") == []            # بلا slug
    # slug وهمي بلا توكن → آمن (يُرجع [] لا يرمي)
    assert isinstance(ga.collect_pull_requests("owner/repo"), list)


def test_collect_activity_only_commits_without_token(repo, monkeypatch):
    from core import git_activity as ga
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    _commit(repo, "f.py", "a\n", "c1")
    act = ga.collect_activity(repo, with_prs=False)
    assert len(act) == 1 and act[0]["kind"] == "commit"
    assert all(a["kind"] == "commit" for a in act)


# ── التخزين والكاش ───────────────────────────────────────────────────────────

def test_activity_cached_and_read(repo):
    from core import git_activity as ga
    _commit(repo, "f.py", "a\nb\n", "c1")
    ga.collect_activity(repo, with_prs=False)
    cached = ga.read_cached(cwd=repo)
    assert cached and cached[0]["message"] == "c1"


def test_pending_commit_marked(repo):
    from core import git_activity as ga
    e = ga.log_pending_commit(repo, "سيتم الإنشاء", 12, 0)
    assert e["pending"] is True and e["hash"] == "pending"
    assert any(x.get("pending") for x in ga.read_cached(cwd=repo))


def test_cache_is_per_project(repo, tmp_path):
    """كاش النشاط لكل مشروع: لا تُعرَض بيانات مستودع في مستودع آخر."""
    from core import git_activity as ga
    import subprocess
    _commit(repo, "a.py", "x\n", "من المشروع A")
    ga.collect_activity(repo, with_prs=False)
    # مشروع ثانٍ منفصل
    repo_b = tmp_path / "proj_b"
    repo_b.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo_b)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo_b)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo_b)
    (repo_b / "b.py").write_text("y\n")
    subprocess.run(["git", "add", "-A"], cwd=repo_b)
    subprocess.run(["git", "commit", "-qm", "من المشروع B"], cwd=repo_b)
    ga.collect_activity(str(repo_b), with_prs=False)
    # كلٌّ يرى سجلّه فقط
    a = ga.read_cached(cwd=repo)
    b = ga.read_cached(cwd=str(repo_b))
    assert a and a[0]["message"] == "من المشروع A"
    assert b and b[0]["message"] == "من المشروع B"


# ── endpoint + الترقيم ───────────────────────────────────────────────────────

def _srv(tmp_path, monkeypatch, repo):
    from web import server
    monkeypatch.setattr(server, "WEAVER_ROOT", __import__("pathlib").Path(repo))
    # لا مساحة عمل نشِطة → يستخدم WEAVER_ROOT (وهو المستودع)
    monkeypatch.setattr(server, "_active_workspace", lambda: {})
    return server


def test_api_git_activity_pagination(repo, tmp_path, monkeypatch):
    for i in range(5):
        _commit(repo, f"f{i}.py", "x\n" * (i + 1), f"commit {i}")
    server = _srv(tmp_path, monkeypatch, repo)
    r = server._api_git_activity(limit=2, offset=0, refresh=True)
    assert r["total"] == 5 and len(r["activity"]) == 2 and r["has_more"] is True
    r2 = server._api_git_activity(limit=2, offset=4)
    assert r2["has_more"] is False and len(r2["activity"]) == 1


def test_api_git_activity_safe_without_repo(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "WEAVER_ROOT", tmp_path / "nope")
    monkeypatch.setattr(server, "_active_workspace", lambda: {})
    monkeypatch.setenv("WEAVER_DB_PATH", str(tmp_path / "m.db"))
    r = server._api_git_activity(refresh=True)
    assert r["activity"] == [] and r["total"] == 0
