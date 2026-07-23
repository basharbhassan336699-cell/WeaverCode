"""
oplog.py — سجل عمليات التعديل (Operations Log) لـ WeaverCode
============================================================

يتتبّع كل تعديل ملف (إنشاء/تعديل) مع عدد الأسطر المضافة والمحذوفة (difflib عبر
core/diff_preview)، بصيغة Claude Code: «Edited file  +N -N».

يُكتب JSONL في ~/.weaver/operations.jsonl (مشترك بين الطرفية والويب) ويُقرأ
عبر read_operations() لعرضه في لوحة الويب أو استرجاعه لاحقاً.

EN: Per-edit diff stats (+added/-removed via difflib) appended to a shared JSONL
operations log, readable by both the CLI and the web dashboard.
"""

from __future__ import annotations

import json
import os
import time
from typing import List


def _log_file() -> str:
    base = os.path.dirname(os.path.expanduser(
        os.environ.get("WEAVER_DB_PATH", "~/.weaver/memory.db")))
    return os.path.join(base, "operations.jsonl")


def log_operation(path: str, action: str, added: int, removed: int) -> dict:
    """يسجّل عملية تعديل ويُرجع مدخلها. action: edited|created|extracted…"""
    entry = {"file": os.path.basename(path), "path": str(path),
             "action": action, "added": int(added), "removed": int(removed),
             "ts": time.time()}
    try:
        f = _log_file()
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def read_operations(limit: int = 100) -> List[dict]:
    """آخر عمليات التعديل (الأحدث أولاً)."""
    try:
        with open(_log_file(), "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
        out = []
        for ln in lines:
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
        return list(reversed(out))
    except Exception:
        return []


def clear_operations() -> None:
    try:
        os.remove(_log_file())
    except Exception:
        pass


def stat_label(entry: dict) -> str:
    """صيغة العرض: «Edited main.py  +12 -3» (كما في Claude Code)."""
    verb = {"created": "Created", "edited": "Edited"}.get(
        entry.get("action", "edited"), entry.get("action", "Edited").title())
    return f"{verb} {entry.get('file','?')}  +{entry.get('added',0)} -{entry.get('removed',0)}"
