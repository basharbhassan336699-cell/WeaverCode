"""
git_activity.py — تتبّع نشاط Git/GitHub لـ WeaverCode
=====================================================

يجمع نشاط المستودع (commits + Pull Requests) لعرضه في «شريط نشاط Git» بلوحة
الويب، بأسلوب واجهة Claude Code (شارة `+Added -Removed`، حالة CI/Merged).

- **commits** محلياً عبر `git` (subprocess): hash قصير، الفرع، +/-، الرسالة.
- **PRs + CI** عبر GitHub REST API (urllib، بلا تبعيات) إن توفّر توكن —
  يُقرأ من `GITHUB_TOKEN` أو ارتباط GitHub. **يتعامل بأمان مع غياب التوكن**.

التخزين: `~/.weaver/git_activity.jsonl` (نفس نمط operations.jsonl). لا يمسّ هذا
الملف مصادقة provider.py.

EN: Collects repo activity (local commits via git + PRs/CI via GitHub API when a
token is available; degrades gracefully without one) for the web dashboard's
Git activity bar. Cached to git_activity.jsonl.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Dict, List, Optional


def _activity_file(cwd: str = "") -> str:
    """ملف كاش النشاط. مفتاح لكل مشروع (cwd) كي لا تختلط سجلات مستودع بآخر.

    المشكلة سابقاً: ملف كاش عالمي واحد → عند التبديل بين المشاريع تُعرَض بيانات
    المشروع السابق (لا المشروع النشط). الآن لكل مساحة عمل ملفها الخاص، فتعرض
    اللوحة دائماً سجل «المشروع الذي نعمل عليه».
    """
    base = os.path.dirname(os.path.expanduser(
        os.environ.get("WEAVER_DB_PATH", "~/.weaver/memory.db")))
    if cwd:
        try:
            key = os.path.realpath(cwd)
        except Exception:
            key = cwd
        import hashlib
        h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        return os.path.join(base, "git_activity_" + h + ".jsonl")
    return os.path.join(base, "git_activity.jsonl")


def _run_git(args: List[str], cwd: str, timeout: int = 15) -> str:
    try:
        r = subprocess.run(["git", *args], capture_output=True, text=True,
                           cwd=cwd, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def is_git_repo(cwd: str) -> bool:
    return _run_git(["rev-parse", "--is-inside-work-tree"], cwd) == "true"


def repo_slug(cwd: str) -> str:
    """owner/repo من remote origin (إن كان GitHub)، وإلا ''."""
    remote = _run_git(["remote", "get-url", "origin"], cwd)
    m = re.search(r"github\.com[:/]+([^/]+/[^/.\s]+)", remote or "")
    return m.group(1) if m else ""


# ── جمع الـ commits محلياً ────────────────────────────────────────────────────

def collect_commits(cwd: str, limit: int = 30) -> List[dict]:
    """آخر commits مع hash/الفرع/+المضاف/-المحذوف/الرسالة. الأحدث أولاً."""
    if not is_git_repo(cwd):
        return []
    branch = _run_git(["branch", "--show-current"], cwd) or "HEAD"
    slug = repo_slug(cwd)
    # سطر لكل commit: hash|author-time|subject
    raw = _run_git(["log", f"-{limit}", "--no-merges",
                    "--pretty=format:%h\x1f%ct\x1f%s"], cwd)
    commits: List[dict] = []
    for line in (raw.splitlines() if raw else []):
        parts = line.split("\x1f")
        if len(parts) < 3:
            continue
        h, ct, subject = parts[0], parts[1], parts[2]
        added, removed = _commit_numstat(cwd, h)
        commits.append({
            "kind": "commit", "hash": h, "branch": branch, "repo": slug,
            "message": subject, "added": added, "removed": removed,
            "ts": _int(ct), "pending": False,
        })
    return commits


def _commit_numstat(cwd: str, h: str) -> tuple:
    """(added, removed) لِـ commit عبر git show --numstat."""
    out = _run_git(["show", "--numstat", "--format=", h], cwd)
    added = removed = 0
    for ln in (out.splitlines() if out else []):
        cols = ln.split("\t")
        if len(cols) >= 2 and cols[0].isdigit() and cols[1].isdigit():
            added += int(cols[0])
            removed += int(cols[1])
    return added, removed


def _int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


# ── جمع الـ Pull Requests عبر GitHub API ─────────────────────────────────────

def github_token() -> str:
    """توكن GitHub: من GITHUB_TOKEN أو ارتباط github. '' إن لم يوجد (آمن)."""
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("WEAVER_GITHUB_TOKEN") or ""
    if tok.strip():
        return tok.strip()
    try:  # ارتباط GitHub في integrations.json (اختياري)
        from pathlib import Path
        f = Path(os.path.expanduser("~")) / ".weaver" / "integrations.json"
        # المسار الفعلي في المشروع؛ نجرّب config/integrations.json أيضاً
        for p in (f, Path(__file__).resolve().parent.parent / "config" / "integrations.json"):
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                items = data if isinstance(data, list) else data.get("integrations", [])
                for it in items:
                    if it.get("id") == "github" and it.get("token"):
                        return str(it["token"]).strip()
    except Exception:
        pass
    return ""


def _gh_get(url: str, token: str, timeout: int = 12):
    """GET JSON من GitHub API عبر urllib ثم curl (Termux). (data, error)."""
    import urllib.request
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "WeaverCode"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception:
        try:
            args = ["curl", "-sS", url, "--max-time", str(timeout)]
            for k, v in headers.items():
                args += ["-H", f"{k}: {v}"]
            out = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 5)
            return json.loads(out.stdout), None
        except Exception as e:
            return None, str(e)


def collect_pull_requests(slug: str, limit: int = 20) -> List[dict]:
    """آخر Pull Requests مع الحالة (open/merged/closed) وحالة CI. آمن بلا توكن.

    بلا توكن أو بلا slug → [] (لا يفشل، لا يفترض).
    """
    if not slug:
        return []
    token = github_token()
    data, err = _gh_get(
        f"https://api.github.com/repos/{slug}/pulls?state=all&per_page={limit}&sort=updated&direction=desc",
        token)
    if err or not isinstance(data, list):
        return []  # غياب التوكن/الشبكة → آمن
    prs: List[dict] = []
    for pr in data:
        if not isinstance(pr, dict):
            continue
        merged = bool(pr.get("merged_at"))
        state = "merged" if merged else pr.get("state", "open")
        ci = _ci_status(slug, pr.get("head", {}).get("sha", ""), token) if token else "unknown"
        prs.append({
            "kind": "pr", "number": pr.get("number"), "repo": slug,
            "branch": pr.get("head", {}).get("ref", ""),
            "title": pr.get("title", ""), "state": state, "ci": ci,
            "added": pr.get("additions"), "removed": pr.get("deletions"),
            "url": pr.get("html_url", ""),
            "ts": _parse_ts(pr.get("updated_at")), "pending": False,
        })
    return prs


def _ci_status(slug: str, sha: str, token: str) -> str:
    """حالة CI لـ commit: success|failure|pending|unknown (آمن)."""
    if not sha or not token:
        return "unknown"
    data, err = _gh_get(f"https://api.github.com/repos/{slug}/commits/{sha}/status", token)
    if err or not isinstance(data, dict):
        return "unknown"
    st = data.get("state", "")
    return {"success": "success", "failure": "failure", "error": "failure",
            "pending": "pending"}.get(st, "unknown")


def _parse_ts(iso: Optional[str]) -> int:
    if not iso:
        return 0
    try:
        import calendar
        return int(calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))
    except Exception:
        return 0


# ── التجميع + التخزين ─────────────────────────────────────────────────────────

def collect_activity(cwd: str, commit_limit: int = 30, pr_limit: int = 20,
                     with_prs: bool = True) -> List[dict]:
    """يجمع commits (+PRs إن أمكن) مرتّبة بالأحدث أولاً، ويحدّث ملف الكاش."""
    items = collect_commits(cwd, commit_limit)
    slug = repo_slug(cwd)
    if with_prs and slug:
        try:
            items += collect_pull_requests(slug, pr_limit)
        except Exception:
            pass
    items.sort(key=lambda x: x.get("ts", 0), reverse=True)
    _cache_write(items, cwd)
    return items


def _cache_write(items: List[dict], cwd: str = "") -> None:
    try:
        f = _activity_file(cwd)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "w", encoding="utf-8") as fh:
            for it in items:
                fh.write(json.dumps(it, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_cached(limit: int = 50, cwd: str = "") -> List[dict]:
    """يقرأ آخر نشاط مُخزَّن لمشروع محدّد (بلا git/شبكة) — للاستجابة السريعة.

    cwd يحدّد المشروع؛ فلا تُقرأ بيانات مشروع آخر. بلا cwd → الملف العالمي القديم.
    """
    try:
        with open(_activity_file(cwd), "r", encoding="utf-8") as fh:
            items = [json.loads(l) for l in fh if l.strip()]
        items.sort(key=lambda x: x.get("ts", 0), reverse=True)
        return items[:limit]
    except Exception:
        return []


def log_pending_commit(cwd: str, message: str, added: int = 0, removed: int = 0) -> dict:
    """يسجّل commit «معلّق» (وضع التخطيط): معاينة لما سيحدث دون تنفيذ فعلي."""
    entry = {"kind": "commit", "hash": "pending", "branch":
             _run_git(["branch", "--show-current"], cwd) or "HEAD",
             "repo": repo_slug(cwd), "message": message,
             "added": int(added), "removed": int(removed),
             "ts": int(time.time()), "pending": True}
    try:
        f = _activity_file(cwd)   # لكل مشروع (نفس مفتاح القراءة)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry
