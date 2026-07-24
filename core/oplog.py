"""
oplog.py — سجل عمليات هرمي بثلاث مستويات لـ WeaverCode
=====================================================

يتتبّع عمليات الوكيل (تعديل/إنشاء/قراءة/تنفيذ) مع ما يكفي لإعادة بناء ثلاثة
مستويات عرض (كواجهة Claude Code):

  المستوى 1 — ملخّص الدفعة:  "Edited 3 files, ran 2 commands, read 1 file"
  المستوى 2 — قائمة العمليات: كل عملية بسطر (ملف/نوع/+N -N)
  المستوى 3 — تفاصيل عملية:   diff (قبل/بعد)، أمر+مخرجات، أو محتوى كامل

كل عملية لها `id` فريد و`batch_id` يجمع عمليات رد النموذج الواحد. تُخزَّن كل
البيانات (المحتوى قبل/بعد، الأوامر ومخرجاتها) في operations.jsonl فيُعاد بناء
المستوى 3 دون قراءة القرص من جديد.

EN: Hierarchical (3-level) operations log — batch summary → op list → full detail
(diff / command+output / content) — persisted with enough data in JSONL to
rebuild every level without re-reading files. Backward compatible with the old
log_operation(path, action, added, removed) call.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Dict, List, Optional

# حدّ لحجم المحتوى المخزَّن لكل حقل (قبل/بعد/مخرجات/محتوى) — يكفي للعرض بلا تضخّم
_MAX_FIELD = 20000

# الدفعة الحالية (رد نموذج واحد). تُضبَط عبر start_batch() من محرّك الوكيل.
_current_batch: Optional[str] = None


def _log_file() -> str:
    base = os.path.dirname(os.path.expanduser(
        os.environ.get("WEAVER_DB_PATH", "~/.weaver/memory.db")))
    return os.path.join(base, "operations.jsonl")


def _clip(v):
    if isinstance(v, str) and len(v) > _MAX_FIELD:
        return v[:_MAX_FIELD] + f"\n… [اقتُطع {len(v) - _MAX_FIELD} حرف]"
    return v


# ── إدارة الدفعات (batch = عمليات رد نموذج واحد) ──────────────────────────────

def start_batch() -> str:
    """يبدأ دفعة جديدة ويجعلها الحالية. يُستدعى في بداية تنفيذ أدوات كل دور."""
    global _current_batch
    _current_batch = uuid.uuid4().hex[:12]
    return _current_batch


def current_batch() -> str:
    """معرّف الدفعة الحالية (يُنشئ واحدة إن لم توجد)."""
    global _current_batch
    if not _current_batch:
        _current_batch = uuid.uuid4().hex[:12]
    return _current_batch


# ── التسجيل ──────────────────────────────────────────────────────────────────

def log_operation(path: str = "", action: str = "edited",
                  added: int = 0, removed: int = 0, *,
                  op_type: Optional[str] = None,
                  before: Optional[str] = None, after: Optional[str] = None,
                  command: Optional[str] = None, output: Optional[str] = None,
                  content: Optional[str] = None,
                  batch_id: Optional[str] = None) -> dict:
    """يسجّل عملية ويُرجع مدخلها الكامل.

    متوافق للخلف: log_operation(path, action, added, removed) يعمل كما كان.
    op_type: edit|create|read|run (يُشتق من action إن لم يُمرَّر).
    """
    if op_type is None:
        op_type = {"edited": "edit", "created": "create",
                   "read": "read", "run": "run"}.get(action, action or "edit")
    entry = {
        "id": uuid.uuid4().hex[:12],
        "batch_id": batch_id or current_batch(),
        "file": os.path.basename(path) if path else "",
        "path": str(path),
        "type": op_type,
        "action": action,
        "added": int(added), "removed": int(removed),
        "ts": time.time(),
    }
    # حقول المستوى 3 (تُخزَّن فقط إن وُجدت لتوفير الحجم)
    for k, v in (("before", before), ("after", after),
                 ("command", command), ("output", output), ("content", content)):
        if v is not None:
            entry[k] = _clip(v)
    try:
        f = _log_file()
        os.makedirs(os.path.dirname(f), exist_ok=True)
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


# ── القراءة ──────────────────────────────────────────────────────────────────

def read_operations(limit: int = 200) -> List[dict]:
    """آخر العمليات (الأحدث أولاً)."""
    try:
        with open(_log_file(), "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-limit:]
    except Exception:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return list(reversed(out))


def read_operation(op_id: str) -> Optional[dict]:
    """تفاصيل عملية واحدة بمعرّفها (المستوى 3) — أو None."""
    if not op_id:
        return None
    try:
        with open(_log_file(), "r", encoding="utf-8") as fh:
            for ln in fh:
                try:
                    o = json.loads(ln)
                except Exception:
                    continue
                if o.get("id") == op_id:
                    return o
    except Exception:
        pass
    return None


def read_batches(limit_batches: int = 50, limit_ops: int = 1000) -> List[dict]:
    """يجمّع العمليات في دفعات (المستوى 1+2). الأحدث أولاً.

    كل دفعة: {batch_id, summary, ts, count, operations:[...]}.
    """
    ops = list(reversed(read_operations(limit_ops)))  # الأقدم أولاً للحفاظ على الترتيب
    order: List[str] = []
    groups: Dict[str, List[dict]] = {}
    for o in ops:
        b = o.get("batch_id") or "—"
        if b not in groups:
            groups[b] = []
            order.append(b)
        groups[b].append(o)
    batches = []
    for b in order:
        items = groups[b]
        batches.append({
            "batch_id": b,
            "summary": summarize_batch(items),
            "ts": max((x.get("ts", 0) for x in items), default=0),
            "count": len(items),
            "operations": [op_line(x) for x in items],
        })
    batches.reverse()  # الأحدث أولاً
    return batches[:limit_batches]


def clear_operations() -> None:
    try:
        os.remove(_log_file())
    except Exception:
        pass


# ── الملخّص والعناوين ────────────────────────────────────────────────────────

_VERB = {"edit": "Edited", "create": "Created", "read": "Read", "run": "Ran"}
_ICON = {"edit": "✏️", "create": "📄", "read": "📖", "run": "💻"}


def summarize_batch(ops: List[dict]) -> str:
    """المستوى 1: «Edited 3 files, ran 2 commands, read 1 file»."""
    counts: Dict[str, int] = {}
    for o in ops:
        t = o.get("type", "edit")
        counts[t] = counts.get(t, 0) + 1
    parts = []
    # ترتيب ثابت: تعديل، إنشاء، تنفيذ، قراءة
    if counts.get("edit"):
        n = counts["edit"]; parts.append(f"Edited {n} file{'s' if n > 1 else ''}")
    if counts.get("create"):
        n = counts["create"]; parts.append(f"created {n} file{'s' if n > 1 else ''}")
    if counts.get("run"):
        n = counts["run"]; parts.append(f"ran {n} command{'s' if n > 1 else ''}")
    if counts.get("read"):
        n = counts["read"]; parts.append(f"read {n} file{'s' if n > 1 else ''}")
    # أنواع أخرى غير متوقّعة
    for t, n in counts.items():
        if t not in ("edit", "create", "run", "read"):
            parts.append(f"{t} {n}")
    return ", ".join(parts) if parts else "لا عمليات"


def op_line(o: dict) -> dict:
    """المستوى 2: بيانات سطر عملية (بلا المحتوى الثقيل)."""
    t = o.get("type", "edit")
    label = o.get("file") or (o.get("command", "")[:40] if t == "run" else "")
    return {
        "id": o.get("id", ""),
        "type": t,
        "icon": _ICON.get(t, "•"),
        "verb": _VERB.get(t, t.title()),
        "file": o.get("file", ""),
        "path": o.get("path", ""),
        "label": label,
        "added": o.get("added", 0),
        "removed": o.get("removed", 0),
        "ts": o.get("ts", 0),
    }


def stat_label(entry: dict) -> str:
    """صيغة سطر مختصرة: «Edited main.py  +12 -3» (توافق للخلف)."""
    verb = _VERB.get(entry.get("type", ""),
                     {"created": "Created", "edited": "Edited"}.get(
                         entry.get("action", "edited"),
                         entry.get("action", "Edited").title()))
    return (f"{verb} {entry.get('file', '?')}  "
            f"+{entry.get('added', 0)} -{entry.get('removed', 0)}")
