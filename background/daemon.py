"""
daemon.py — تشغيل WeaverCode في الخلفية.
يقرأ المهام من طابور (task_queue.json)، ينفّذها، ويبثّ الأحداث عبر EventBus.
"""

import asyncio
import sys
import os
import signal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.engine.provider import get_provider, Message  # noqa: E402
from core.engine.query_engine import QueryEngine        # noqa: E402
from core.tools.registry import ToolRegistry            # noqa: E402
from core.memory.store import MemoryStore               # noqa: E402
from prompts.system import get_system_prompt            # noqa: E402
from background.events import event_bus, WeaverEvent, EventType  # noqa: E402
from background import status as st                      # noqa: E402


def _reload_env() -> None:
    """يعيد تحميل config/.env ويحدّث os.environ (مزامنة الويب ← الخادم الخلفي).

    ما يُحفظ من واجهة الويب يُكتب في config/.env؛ هذا يجعل الـ daemon يلتقط
    التغيير في المهمة التالية دون إعادة تشغيل. يقرأ نفس الملف المصدر — آمن،
    ولا يمسّ منطق المصادقة (فقط يُحدِّث القيم من .env).
    """
    try:
        f = Path(__file__).resolve().parent.parent / "config" / ".env"
        if not f.exists():
            return
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k:
                os.environ[k] = v
    except Exception:
        pass


def _outputs_dir() -> str:
    """مجلد المخرجات — نفس منطق web/server._outputs_dir ليتطابق مع شاشة «الملفات».

    نجعله مجلد عمل الوكيل حتى تظهر الملفات المُنشأة (بمسارات نسبية) فوراً في
    شاشة الملفات وتكون قابلة للتنزيل — بدل أن تُكتب في جذر المستودع غير المرئي.
    """
    env = os.environ.get("WEAVER_OUTPUTS")
    if env:
        p = Path(os.path.expanduser(env))
    else:
        termux = Path(os.path.expanduser("~/storage/downloads/WeaverCode_outputs"))
        p = termux if termux.parent.exists() else Path(os.path.expanduser("~/WeaverCode_outputs"))
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        return os.getcwd()
    return str(p)


class WeaverDaemon:
    def __init__(self):
        self.running = False
        # في الخلفية لا يمكن السؤال التفاعلي؛ ننفّذ تلقائياً (حماية Bash تبقى فعّالة).
        # عطّلها بـ WEAVER_DAEMON_AUTO_APPROVE=0 (عندها تُرفض أدوات التعديل).
        self.auto_approve = os.environ.get(
            "WEAVER_DAEMON_AUTO_APPROVE", "1").strip().lower() in ("1", "true", "yes", "on")

    async def start(self):
        self.running = True
        st.save_status("idle")
        await event_bus.emit(WeaverEvent(EventType.STATUS, "daemon يعمل", "idle"))
        while self.running:
            task = st.pop_task()
            if task:
                try:
                    await self._run_task(task["prompt"], task.get("mode", "main"),
                                         task.get("history"),
                                         task.get("session_id", ""))
                except Exception as e:
                    await event_bus.emit(WeaverEvent(EventType.ERROR, str(e)))
                    st.save_status("idle")
            await asyncio.sleep(0.5)

    async def _run_task(self, prompt: str, mode: str = "main", history=None,
                        session_id: str = ""):
        st.save_status("working", prompt)
        await event_bus.emit(WeaverEvent(EventType.THINKING, "يعالج المهمة...", prompt))

        _reload_env()  # مزامنة: التقاط تغييرات الإعدادات من الويب (config/.env)
        provider = get_provider()
        # مجلد العمل = مجلد المخرجات: يضمن ظهور الملفات المُنشأة في شاشة «الملفات»
        tools = ToolRegistry(work_dir=_outputs_dir())
        memory = MemoryStore()
        engine = QueryEngine(
            provider=provider,
            tool_registry=tools,
            memory=memory,
            system_prompt=get_system_prompt(mode),
        )
        if self.auto_approve:
            engine.auto_approve = True

        loop = asyncio.get_event_loop()

        def on_tool(name, args):
            detail = ""
            if args:
                try:
                    detail = str(list(args.values())[0])[:80]
                except Exception:
                    detail = ""
            etype = {
                "Read": EventType.FILE_VIEW,
                "Write": EventType.FILE_CREATE,
                "Edit": EventType.FILE_EDIT,
                "MultiEdit": EventType.FILE_EDIT,
                "Bash": EventType.BASH_RUN,
            }.get(name, EventType.TOOL_START)
            msg = {
                EventType.FILE_VIEW: "يقرأ ملفاً",
                EventType.FILE_CREATE: f"ينشئ {detail}",
                EventType.FILE_EDIT: "يعدّل ملفاً",
                EventType.BASH_RUN: "ينفّذ أمراً",
            }.get(etype, f"يستخدم {name}")
            # on_tool متزامن؛ نجدول البثّ في الحلقة
            asyncio.run_coroutine_threadsafe(
                event_bus.emit(WeaverEvent(etype, msg, detail)), loop)

        # تحويل سجل المحادثة (إن وُجد) إلى رسائل لتستمر المحادثة بسياق
        hist_msgs = None
        if history:
            hist_msgs = []
            for h in history:
                role = h.get("role")
                content = h.get("content", "")
                if role in ("user", "assistant") and content:
                    hist_msgs.append(Message(role=role, content=content))

        result = await engine.run(prompt, history=hist_msgs, on_tool=on_tool)

        response_text = ""
        if result.error:
            await event_bus.emit(WeaverEvent(EventType.ERROR, result.error))
        else:
            text = result.text
            if not text or not text.strip():
                raw = (getattr(provider, "last_raw", "") or "").strip()
                text = "(لم يُرجع النموذج نصاً — جرّب صياغة أوضح أو نموذجاً آخر.)"
                if raw:
                    text += f"\n\n🔎 آخر استجابة خام من المزوّد (تشخيص):\n{raw[:800]}"
            response_text = text
            await event_bus.emit(WeaverEvent(EventType.RESPONSE, text[:200], text))

        # ── حفظ المحادثة كجلسة واحدة (لا رسالة منفصلة لكل دور) ────────────────
        # يجمع كل الدورة (السجل السابق + رسالة المستخدم + رد الوكيل) في صفّ واحد
        # بجدول sessions، فتظهر المحادثة كعنصر واحد في القائمة الخارجية.
        if session_id:
            try:
                msgs = list(history or [])
                msgs.append({"role": "user", "content": prompt})
                if response_text:
                    msgs.append({"role": "assistant", "content": response_text})
                # اسم الجلسة = أول رسالة مستخدم في المحادثة
                first_user = next((m.get("content", "") for m in msgs
                                   if m.get("role") == "user"), prompt)
                name = (first_user or prompt)[:50]
                import json as _json
                memory.save_session(session_id, name, prompt,
                                    _json.dumps(msgs, ensure_ascii=False))
            except Exception:
                pass

        await event_bus.emit(WeaverEvent(EventType.DONE, "اكتملت المهمة"))
        st.save_status("idle")

    def stop(self):
        self.running = False
        st.save_status("stopped")


async def daemon_main():
    daemon = WeaverDaemon()

    def handle_signal(sig, frame):
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    print(f"🕸️ WeaverCode Daemon started (PID: {os.getpid()})")
    await daemon.start()


if __name__ == "__main__":
    asyncio.run(daemon_main())
