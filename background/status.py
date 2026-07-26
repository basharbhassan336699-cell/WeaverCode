"""
status.py — حالة daemon اللحظية (تُكتب في ملف JSON ليقرأها الويب).
"""

import os
import json
import time
from pathlib import Path

STATUS_FILE = Path(os.path.expanduser(
    os.environ.get("WEAVER_STATUS_FILE", "~/.weaver/daemon_status.json")))
QUEUE_FILE = Path(os.path.expanduser(
    os.environ.get("WEAVER_QUEUE_FILE", "~/.weaver/task_queue.json")))
# راية إيقاف المهمة الجارية (زر «توقيف» في الويب) — يفحصها المحرّك بين الدورات.
CANCEL_FILE = Path(os.path.expanduser(
    os.environ.get("WEAVER_CANCEL_FILE", "~/.weaver/cancel.flag")))


def save_status(state: str, task: str = "", pid: int = 0) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps({
        "state": state,
        "task": task,
        "pid": pid or os.getpid(),
        "timestamp": time.time(),
    }, ensure_ascii=False))


def read_status() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"state": "offline", "task": "", "pid": None, "timestamp": 0}


def queue_task(prompt: str, mode: str = "main", history=None,
               session_id: str = "") -> int:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tasks = read_queue()
    tasks.append({"prompt": prompt, "mode": mode,
                  "history": history or [], "session_id": session_id,
                  "timestamp": time.time()})
    QUEUE_FILE.write_text(json.dumps(tasks, ensure_ascii=False))
    return len(tasks)


def read_queue() -> list:
    if QUEUE_FILE.exists():
        try:
            return json.loads(QUEUE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def pop_task():
    tasks = read_queue()
    if not tasks:
        return None
    task = tasks.pop(0)
    QUEUE_FILE.write_text(json.dumps(tasks, ensure_ascii=False))
    return task


def clear_queue() -> int:
    """يُفرغ طابور المهام المعلّقة (لزر «توقيف»). يُرجع عدد ما أُزيل."""
    n = len(read_queue())
    try:
        QUEUE_FILE.write_text("[]")
    except Exception:
        pass
    return n


# ── راية الإيقاف: يضبطها الويب، يفحصها المحرّك بين الدورات، ويمسحها عند البدء ──
def request_cancel() -> None:
    CANCEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        CANCEL_FILE.write_text(str(time.time()))
    except Exception:
        pass


def is_cancelled() -> bool:
    return CANCEL_FILE.exists()


def clear_cancel() -> None:
    try:
        CANCEL_FILE.unlink()
    except Exception:
        pass
