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


def _active_work_dir() -> str:
    """مجلد عمل الوكيل: مستودع GitHub المستنسَخ إن اختير، وإلا مجلد المخرجات.

    يقرأ config/workspace.json الذي يكتبه الويب عند اختيار مستودع — فيعمل الوكيل
    على ملفات المستودع الحقيقية (بدل اختراع مسارات وهمية) ثم يُرفَع إليها.
    """
    try:
        f = Path(__file__).resolve().parent.parent / "config" / "workspace.json"
        if f.exists():
            import json as _json
            d = _json.loads(f.read_text(encoding="utf-8"))
            wd = d.get("work_dir")
            if wd and os.path.isdir(wd):
                return wd
    except Exception:
        pass
    return _outputs_dir()


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
        st.clear_cancel()   # راية إيقاف قديمة يجب ألّا توقف مهمة جديدة
        st.save_status("working", prompt)
        await event_bus.emit(WeaverEvent(EventType.THINKING, "يعالج المهمة...", prompt))

        _reload_env()  # مزامنة: التقاط تغييرات الإعدادات من الويب (config/.env)
        provider = get_provider()
        # مجلد العمل = المستودع المستنسَخ إن اختير، وإلا مجلد المخرجات.
        tools = ToolRegistry(work_dir=_active_work_dir())
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

        # ── حفظ الجلسة (تدريجي): يُستدعى مبكّراً + عند الخطأ + عند الانتهاء ──────
        # يمنع ضياع المحادثة عند 404/مهلة/إغلاق التطبيق أثناء العمل: رسالة المستخدم
        # تُحفَظ فوراً قبل التنفيذ، ثم تُحدَّث بالردّ لاحقاً.
        def _persist(resp_text: str = "", blocks=None) -> None:
            if not session_id:
                return
            try:
                # نحافظ على كتل العمليات (blocks) من الأدوار السابقة إن أرسلها الويب
                msgs = list(history or [])
                msgs.append({"role": "user", "content": prompt})
                if resp_text:
                    a_msg = {"role": "assistant", "content": resp_text}
                    if blocks:
                        a_msg["blocks"] = blocks   # سجل العمليات (لاسترجاعه بعد التحديث)
                    msgs.append(a_msg)
                first_user = next((m.get("content", "") for m in msgs
                                   if m.get("role") == "user"), prompt)
                name = (first_user or prompt)[:50]
                import json as _json
                memory.save_session(session_id, name, prompt,
                                    _json.dumps(msgs, ensure_ascii=False))
            except Exception:
                pass

        _persist("")   # حفظ فوري لرسالة المستخدم قبل بدء التنفيذ

        try:
            result = await engine.run(prompt, history=hist_msgs, on_tool=on_tool)
        except Exception as exc:
            # عطل غير متوقّع: احفظ ما لدينا (رسالة المستخدم على الأقل) ثم أبلغ
            _persist("")
            await event_bus.emit(WeaverEvent(EventType.ERROR, str(exc)))
            await event_bus.emit(WeaverEvent(EventType.DONE, "اكتملت المهمة"))
            st.save_status("idle")
            return

        response_text = ""
        if result.error:
            await event_bus.emit(WeaverEvent(EventType.ERROR, result.error))
        else:
            text = result.text
            if not text or not text.strip():
                # الوكيل نفّذ أدوات لكن لم يكتب نصاً ختامياً → لخّص ما فعله بدل
                # ترك رسالة فارغة أو JSON خام (أوضح وأنفع للمستخدم).
                tools_used = list(result.tool_calls_made or [])
                if tools_used:
                    from collections import Counter
                    c = Counter(tools_used)
                    summary = "، ".join(f"{n}×{k}" if n > 1 else k
                                        for k, n in c.items())
                    text = ("✅ نفّذت العملية عبر الأدوات: " + summary +
                            ".\nراجع شاشة «الملفات» للنتيجة. "
                            "(لم يكتب النموذج ملخّصاً نصياً — يمكنك طلب «لخّص ما فعلت».)")
                else:
                    text = ("(لم يُرجع النموذج نصاً ولم ينفّذ أدوات. غالباً السياق "
                            "كبير جداً أو الطلب غامض — جرّب «محادثة جديدة» أو صياغة أوضح "
                            "أو ارفع WEAVER_MAX_TOKENS.)")
                    raw = (getattr(provider, "last_raw", "") or "").strip()
                    if raw:
                        text += f"\n\n🔎 تشخيص خام:\n{raw[:400]}"
            response_text = text
            await event_bus.emit(WeaverEvent(EventType.RESPONSE, text[:200], text))

        # ── حفظ المحادثة كاملةً + سجل العمليات (blocks) لاسترجاعه بعد التحديث ──
        _saved_blocks = None
        try:
            from core.action_blocks import serialize_block
            _saved_blocks = [serialize_block(b) for b in (result.blocks or [])]
        except Exception:
            _saved_blocks = None
        _persist(response_text, _saved_blocks)

        # ── تذكير التحقق الذاتي: فقط إن كُتبت ملفات ولم يذكر النموذج تحقّقاً ─────
        # (لا نُزعج المحادثات العادية بلا كتابة كود — تفادياً لتذكير بعد «هلا».)
        _wrote_code = any(t in ("Write", "Edit", "MultiEdit")
                          for t in (getattr(result, "tool_calls_made", None) or []))
        _verify_kw = ("✅ تم التحقق", "py_compile", "pytest", "الاختبارات تمر",
                      "tests pass", "✅ ok", "اختبار")
        _verified = any(s in (response_text or "").lower() for s in
                        (k.lower() for k in _verify_kw))
        if _wrote_code and not _verified:
            _rem = ("⚠️ تذكير: تحقّق من الملفات المُنشأة (py_compile/pytest) "
                    "قبل اعتبار المهمة منجزة.")
            await event_bus.emit(WeaverEvent(EventType.RESPONSE, _rem, _rem))

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
