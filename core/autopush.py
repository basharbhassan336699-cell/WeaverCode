"""
autopush.py — رفع تلقائي إلى GitHub عند انتهاء المهمة (اختياري) 🕸️
==================================================================
Optional auto-push: after a task finishes, commit any real changes inside the
work directory and push them to GitHub. Shared by both the terminal agent
(``weaver.py``) and the web daemon (``background/daemon.py``) so the behavior is
identical everywhere.

Controlled by environment variables (all opt-in; **disabled by default**):
    WEAVER_AUTO_PUSH         1/true/yes/on to enable (default 0 → does nothing)
    WEAVER_AUTO_PUSH_BRANCH  target branch (empty = the current branch)
    WEAVER_AUTO_PUSH_REMOTE  target remote (default: origin)

Safety: it only ever runs when explicitly enabled, only commits when there are
actual changes inside a Git repo, uses the local git credentials, and never
raises — any failure is reported through the optional ``notify`` callback and
swallowed, so it can never break a task or touch the provider connection.
"""
from __future__ import annotations

import os
import subprocess
from typing import Callable, Dict, List, Optional

# نوع دالة الإبلاغ الاختيارية: (level, message) حيث level ∈ info/success/error
Notify = Optional[Callable[[str, str], None]]


def is_enabled() -> bool:
    """هل الرفع التلقائي مفعّل؟ (WEAVER_AUTO_PUSH=1/true/yes/on)."""
    return os.environ.get("WEAVER_AUTO_PUSH", "0").strip().lower() in (
        "1", "true", "yes", "on")


def _run(args: List[str], cwd: str, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True,
                          cwd=cwd, timeout=timeout)


def _commit_message(task_summary: str, changed_files: List[str]) -> str:
    """رسالة commit وصفية: من ملخّص المهمة إن وُجد، وإلا من الملفات المُغيَّرة."""
    n = len(changed_files)
    summary = (task_summary or "").strip().replace("\n", " ")
    if summary:
        return f"🕸️ WeaverCode: {summary[:72]}"
    if n == 1:
        return f"🕸️ WeaverCode: update {changed_files[0]}"
    if n <= 4:
        return f"🕸️ WeaverCode: update {', '.join(changed_files[:4])}"
    return f"🕸️ WeaverCode: update {n} files"


def auto_push(work_dir: str, task_summary: str = "",
              notify: Notify = None, force: bool = False) -> Dict:
    """يرفع التغييرات تلقائياً إلى GitHub عند الانتهاء (إن كان مفعّلاً).

    work_dir     : مجلد المستودع.
    task_summary : ملخّص المهمة (يُستخدم لرسالة commit وصفية).
    notify       : دالة اختيارية (level, message) لتوجيه الرسائل للواجهة.
    force        : تجاوز فحص التفعيل (للاختبار/الاستدعاء اليدوي).

    يُرجع dict: {pushed: bool, reason: str, message: str, files: int}.
    مُغلَّف بالكامل: لا يرمي استثناء أبداً، ولا يفعل شيئاً خارج مستودع git أو بلا
    تغييرات — فلا يمسّ أيّ سلوك قائم ولا الاتصال بالمزوّد."""
    def _say(level: str, msg: str) -> None:
        if notify:
            try:
                notify(level, msg)
            except Exception:
                pass

    if not force and not is_enabled():
        return {"pushed": False, "reason": "disabled", "message": "", "files": 0}

    try:
        # (1) داخل مستودع git؟
        inside = _run(["git", "rev-parse", "--is-inside-work-tree"], work_dir, 10)
        if inside.returncode != 0 or inside.stdout.strip() != "true":
            return {"pushed": False, "reason": "not_a_repo", "message": "", "files": 0}

        # (2) هل توجد تغييرات؟
        status = _run(["git", "status", "--porcelain"], work_dir, 10)
        if not status.stdout.strip():
            _say("info", "لا تغييرات جديدة للرفع.")
            return {"pushed": False, "reason": "no_changes", "message": "", "files": 0}

        changed = [ln.strip().split()[-1]
                   for ln in status.stdout.splitlines() if ln.strip()]
        n = len(changed)
        msg = _commit_message(task_summary, changed)

        # (3) add + commit
        _run(["git", "add", "-A"], work_dir, 30)
        commit = _run(["git", "commit", "-m", msg], work_dir, 30)
        combined = (commit.stdout + commit.stderr).lower()
        if commit.returncode != 0 and "nothing to commit" not in combined:
            _say("error", "تعذّر الـ commit: "
                 + (commit.stderr or commit.stdout).strip()[:120])
            return {"pushed": False, "reason": "commit_failed",
                    "message": msg, "files": n}

        # (4) تحديد الفرع والـ remote
        remote = os.environ.get("WEAVER_AUTO_PUSH_REMOTE", "origin").strip() or "origin"
        branch = os.environ.get("WEAVER_AUTO_PUSH_BRANCH", "").strip()
        if not branch:
            br = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], work_dir, 10)
            branch = br.stdout.strip() or "main"

        # (5) push (مع ضبط upstream تلقائياً إن لزم)
        push = _run(["git", "push", remote, branch], work_dir, 90)
        if push.returncode == 0:
            _say("success", f"✅ رُفع إلى GitHub: {remote}/{branch} ({n} ملف)")
            return {"pushed": True, "reason": "ok",
                    "message": f"{remote}/{branch}", "files": n}

        err = (push.stderr or push.stdout or "").strip()
        if any(k in err.lower() for k in ("no upstream", "set-upstream", "has no upstream")):
            push2 = _run(["git", "push", "--set-upstream", remote, branch], work_dir, 90)
            if push2.returncode == 0:
                _say("success", f"✅ رُفع إلى GitHub: {remote}/{branch} (upstream مضبوط)")
                return {"pushed": True, "reason": "ok_upstream",
                        "message": f"{remote}/{branch}", "files": n}
            err = (push2.stderr or push2.stdout or err).strip()

        _say("error", f"تعذّر الرفع: {err[:200]}")
        return {"pushed": False, "reason": "push_failed",
                "message": err[:200], "files": n}

    except Exception as e:
        _say("error", f"تعذّر الرفع التلقائي: {e}")
        return {"pushed": False, "reason": "exception", "message": str(e), "files": 0}
