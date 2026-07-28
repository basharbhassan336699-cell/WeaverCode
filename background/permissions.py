"""
permissions.py — تنسيق طلبات الإذن بين المحرّك (daemon) ولوحة الويب.

عند تفعيل «وضع الإذن» (WEAVER_ASK_PERMISSION)، يطلب المحرّك موافقة المستخدم قبل
الأدوات الحسّاسة (Bash/Write/Edit/GitPush…). هذا الوسيط يحمل الطلب المعلّق، ويحجب
المحرّك حتى يردّ المستخدم من الويب (allow/deny) أو تنتهي المهلة (deny آمن).

EN: Bridges permission requests between the (blocking) engine callback and the web
UI. Thread-safe: the daemon thread blocks on an Event; a web-server thread resolves
it. Default behavior is unchanged unless ask-mode is enabled.
"""

import time
import uuid
import threading

_lock = threading.Lock()
_event = threading.Event()
_pending = None       # {"id", "name", "arg", "ts"} أو None
_decision = None      # قرار المستخدم للطلب المعلّق


def request(name: str, arg: str = "", timeout: float = 120.0) -> str:
    """يسجّل طلب إذن ويحجب حتى يردّ المستخدم أو تنتهي المهلة.

    يُرجع: "allow_once" | "allow_always" | "deny". عند انتهاء المهلة → "deny".
    (يُستدعى من خيط المحرّك؛ يُحلّ من خيط خادم الويب.)
    """
    global _pending, _decision
    rid = uuid.uuid4().hex[:8]
    with _lock:
        _pending = {"id": rid, "name": name, "arg": (arg or "")[:200], "ts": time.time()}
        _decision = None
        _event.clear()
    got = _event.wait(timeout)
    with _lock:
        dec = _decision
        _pending = None
        _decision = None
    if not got or dec not in ("allow_once", "allow_always", "deny"):
        return "deny"   # مهلة/رفض ضمني → آمن (لا تنفيذ)
    return dec


def pending() -> dict:
    """الطلب المعلّق الحالي (للاستعلام من الويب) أو None."""
    with _lock:
        return dict(_pending) if _pending else None


def resolve(rid: str, decision: str) -> bool:
    """يحلّ الطلب المعلّق بقرار المستخدم. يُرجع True إن طابق الطلب الحالي."""
    global _decision
    with _lock:
        if _pending and _pending.get("id") == rid:
            _decision = decision if decision in (
                "allow_once", "allow_always", "deny") else "deny"
            _event.set()
            return True
    return False
