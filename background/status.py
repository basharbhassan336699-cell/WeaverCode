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


def queue_task(prompt: str, mode: str = "main", history=None) -> int:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tasks = read_queue()
    tasks.append({"prompt": prompt, "mode": mode,
                  "history": history or [], "timestamp": time.time()})
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
