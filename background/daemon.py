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

from core.engine.provider import get_provider          # noqa: E402
from core.engine.query_engine import QueryEngine        # noqa: E402
from core.tools.registry import ToolRegistry            # noqa: E402
from core.memory.store import MemoryStore               # noqa: E402
from prompts.system import get_system_prompt            # noqa: E402
from background.events import event_bus, WeaverEvent, EventType  # noqa: E402
from background import status as st                      # noqa: E402


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
                    await self._run_task(task["prompt"], task.get("mode", "main"))
                except Exception as e:
                    await event_bus.emit(WeaverEvent(EventType.ERROR, str(e)))
                    st.save_status("idle")
            await asyncio.sleep(0.5)

    async def _run_task(self, prompt: str, mode: str = "main"):
        st.save_status("working", prompt)
        await event_bus.emit(WeaverEvent(EventType.THINKING, "يعالج المهمة...", prompt))

        provider = get_provider()
        tools = ToolRegistry()
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

        result = await engine.run(prompt, on_tool=on_tool)

        if result.error:
            await event_bus.emit(WeaverEvent(EventType.ERROR, result.error))
        else:
            await event_bus.emit(WeaverEvent(
                EventType.RESPONSE,
                (result.text or "تم")[:200],
                result.text or ""))
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
