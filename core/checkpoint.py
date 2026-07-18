"""
checkpoint.py — نقاط الاستعادة والتراجع (Checkpoint & Rewind) لـ WeaverCode
==========================================================================

يلتقط لقطة (snapshot) من محتوى الملف *قبل* كل عملية كتابة (Write/Edit/
MultiEdit/NotebookEdit)، فيتيح للمستخدم التراجع عن تغييرات الوكيل واستعادة
الحالة السابقة — كما تفعل ميزة Rewind في Claude Code.

اللقطات تُحفظ في الذاكرة (خفيفة، لكل جلسة). كل نقطة تحمل:
    - رقم تسلسلي (1، 2، 3…)
    - الأداة والمسار
    - محتوى الملف قبل التغيير (None إن كان الملف جديداً)
    - طابع زمني

الاستخدام:
    cm = CheckpointManager()
    cm.snapshot("Edit", "/path/a.py")     # قبل التنفيذ
    ...التنفيذ...
    cm.rewind()                           # استعادة آخر نقطة
    cm.rewind_to(2)                        # استعادة حتى النقطة 2

EN: In-memory checkpoint/rewind. Snapshots a file's prior content before each
write operation so the user can undo the agent's changes. Pure filesystem
restore — never touches the network or provider.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

# أدوات الكتابة التي تستحق لقطة قبل تنفيذها
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# حد أقصى لعدد النقاط المحفوظة (تفادي تضخّم الذاكرة)
_MAX_CHECKPOINTS = 200
# حد أقصى لحجم الملف الملتقَط (2MB)
_MAX_SNAP_BYTES = 2 * 1024 * 1024


@dataclass
class Checkpoint:
    """نقطة استعادة واحدة لملف واحد."""
    seq:        int
    tool:       str
    path:       str
    prev_content: Optional[str]   # None = الملف لم يكن موجوداً
    existed:    bool
    label:      str = ""
    timestamp:  float = field(default_factory=time.time)

    def describe(self) -> str:
        name = Path(self.path).name
        kind = "إنشاء" if not self.existed else "تعديل"
        return f"#{self.seq}  {kind} {name}  ({self.tool})"


class CheckpointManager:
    """يدير لقطات الملفات ويتيح التراجع."""

    def __init__(self, max_checkpoints: int = _MAX_CHECKPOINTS):
        self._checkpoints: List[Checkpoint] = []
        self._seq = 0
        self._max = max_checkpoints

    # ── التقاط ───────────────────────────────────────────────────────────────

    @staticmethod
    def is_write_tool(tool_name: str) -> bool:
        return tool_name in _WRITE_TOOLS

    def snapshot(self, tool: str, path: str,
                 label: str = "") -> Optional[Checkpoint]:
        """
        يلتقط لقطة لحالة الملف قبل تعديله. يُرجع الـ Checkpoint أو None
        (إن كان الملف كبيراً جداً أو تعذّرت القراءة — لا يعطّل التنفيذ).
        """
        if not path:
            return None
        p = Path(path)
        existed = p.exists() and p.is_file()
        prev: Optional[str] = None
        if existed:
            try:
                if p.stat().st_size > _MAX_SNAP_BYTES:
                    return None
                prev = p.read_text(encoding="utf-8", errors="replace")
            except Exception:
                return None
        self._seq += 1
        cp = Checkpoint(seq=self._seq, tool=tool, path=str(p),
                        prev_content=prev, existed=existed, label=label)
        self._checkpoints.append(cp)
        if len(self._checkpoints) > self._max:
            self._checkpoints.pop(0)
        return cp

    # ── استعلام ───────────────────────────────────────────────────────────────

    def list(self) -> List[Checkpoint]:
        """كل النقاط بترتيبها الزمني (الأقدم أولاً)."""
        return list(self._checkpoints)

    def count(self) -> int:
        return len(self._checkpoints)

    def latest(self) -> Optional[Checkpoint]:
        return self._checkpoints[-1] if self._checkpoints else None

    # ── استعادة ───────────────────────────────────────────────────────────────

    def _restore_one(self, cp: Checkpoint) -> bool:
        """يعيد ملفاً واحداً لحالته الملتقَطة. يُرجع True عند النجاح."""
        p = Path(cp.path)
        try:
            if not cp.existed:
                # كان الملف جديداً → نحذفه للعودة للحالة السابقة
                if p.exists():
                    p.unlink()
                return True
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(cp.prev_content or "", encoding="utf-8")
            return True
        except Exception:
            return False

    def rewind(self) -> Optional[Checkpoint]:
        """
        يتراجع عن آخر عملية: يستعيد الملف ويزيل النقطة من السجل.
        يُرجع الـ Checkpoint المُستعاد أو None إن لم يوجد شيء.
        """
        if not self._checkpoints:
            return None
        cp = self._checkpoints.pop()
        self._restore_one(cp)
        return cp

    def rewind_to(self, seq: int) -> List[Checkpoint]:
        """
        يتراجع عن كل العمليات حتى (وشاملةً) النقطة ذات الرقم seq.
        الاستعادة تتم بترتيب عكسي (الأحدث أولاً) لضمان صحة الحالة.

        Returns: قائمة النقاط التي استُعيدت (فارغة إن لم يوجد seq).
        """
        if not any(cp.seq == seq for cp in self._checkpoints):
            return []
        restored: List[Checkpoint] = []
        while self._checkpoints and self._checkpoints[-1].seq >= seq:
            cp = self._checkpoints.pop()
            self._restore_one(cp)
            restored.append(cp)
        return restored

    def clear(self) -> None:
        self._checkpoints.clear()
