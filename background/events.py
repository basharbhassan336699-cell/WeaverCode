"""
events.py — نظام الأحداث اللحظية لـ WeaverCode
يبثّ ما يفعله الوكيل (تفكير/أدوات/ملفات/أوامر) للواجهة عبر ناقل أحداث مركزي.
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List


class EventType(Enum):
    THINKING = "thinking"        # يفكر/يعالج
    TOOL_START = "tool_start"    # بدأ أداة
    TOOL_END = "tool_end"        # انتهى أداة
    FILE_VIEW = "file_view"      # يقرأ ملف
    FILE_EDIT = "file_edit"      # يعدّل ملف
    FILE_CREATE = "file_create"  # ينشئ ملف
    BASH_RUN = "bash_run"        # ينفذ أمر
    RESPONSE = "response"        # رد نهائي
    ERROR = "error"              # خطأ
    DONE = "done"                # انتهى
    STATUS = "status"            # تغيّر حالة الـ daemon


@dataclass
class WeaverEvent:
    type: EventType
    message: str
    detail: str = ""
    diff_added: int = 0
    diff_removed: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "message": self.message,
            "detail": self.detail,
            "diff_added": self.diff_added,
            "diff_removed": self.diff_removed,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventBus:
    """ناقل أحداث مفرد (singleton) بين WeaverCode والواجهة."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.subscribers = []
            cls._instance.history = []
        return cls._instance

    async def emit(self, event: WeaverEvent):
        self.history.append(event)
        if len(self.history) > 200:
            self.history.pop(0)
        for sub in list(self.subscribers):
            try:
                await sub(event)
            except Exception:
                pass

    def subscribe(self, callback: Callable):
        self.subscribers.append(callback)

        def _unsub():
            if callback in self.subscribers:
                self.subscribers.remove(callback)

        return _unsub


# ناقل أحداث عام مشترك
event_bus = EventBus()
