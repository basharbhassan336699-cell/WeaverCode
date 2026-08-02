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
        # ── وضع الإذن (اختياري): يسأل قبل الأدوات الحسّاسة كواجهة Claude Code ──
        # افتراضياً معطّل (WEAVER_ASK_PERMISSION=0) فيبقى التنفيذ التلقائي كما هو،
        # فلا يتغيّر شيء. عند تفعيله: نعطّل auto_approve ونمرّر on_permission يسأل الويب.
        _ask_mode = os.environ.get("WEAVER_ASK_PERMISSION", "0").strip().lower() in (
            "1", "true", "yes", "on")
        _on_permission = None
        if _ask_mode:
            engine.auto_approve = False
            def _on_permission(name, args):   # noqa: E306 (يُستدعى من خيط المحرّك)
                from background import permissions as _perm
                arg = ""
                if isinstance(args, dict):
                    arg = str(args.get("path") or args.get("command")
                              or args.get("url") or args.get("query") or "")
                return _perm.request(name, arg)
        elif self.auto_approve:
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

        # ── نصّ المساعد المُتخلِّل (narration) — كواجهة Claude Code ─────────────
        # يبثّ شرح النموذج القصير بين صناديق الأدوات ليتابع المستخدم «تفكيره» حيّاً
        # (يفكّر بصوت مسموع): «الآن سأتحقّق…» ← صندوق أداة ← «اكتمل، التالي…».
        def _on_narration(text):   # يُستدعى من خيط المحرّك؛ نجدول البثّ في الحلقة
            t = (text or "").strip()
            if not t:
                return
            asyncio.run_coroutine_threadsafe(
                event_bus.emit(WeaverEvent(EventType.NARRATION, t[:200], t)), loop)

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
            result = await engine.run(prompt, history=hist_msgs, on_tool=on_tool,
                                       on_permission=_on_permission,
                                       on_narration=_on_narration)
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

        # ── لقطة شاشة تلقائية للناتج المرئي (كواجهة Claude Code) ───────────────
        # «صورة لما عمله فعلاً» — لا سجل commits: إن أنتجت المهمة ملفاً مرئياً
        # (صفحة/واجهة HTML أو SVG) نلتقط لقطة حقيقية للنتيجة ونعرضها في بطاقة
        # الاكتمال. للمهام غير المرئية (بايثون مثلاً) لا يُلتقط شيء (لا ضجيج).
        if not getattr(result, "error", None):
            await self._auto_shot_result(tools, result, loop)

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

        # ── تحقّق ذاتي تلقائي داخل الـ Sandbox (اختياري، WEAVER_AUTO_VERIFY=1) ──
        # عند التفعيل: بعد كتابة كود، نُصرّف ملفات بايثون تلقائياً (py_compile) —
        # داخل الـ sandbox إن كان مفعّلاً (WEAVER_SANDBOX=1) — ونُبلغ بالنتيجة.
        # معطّل افتراضياً فلا يتغيّر أيّ سلوك قائم. مُغلَّف: أي عطل لا يكسر المهمة.
        _auto_verify = os.environ.get("WEAVER_AUTO_VERIFY", "0").strip().lower() in (
            "1", "true", "yes", "on")
        _did_auto_verify = False
        if _wrote_code and _auto_verify and not getattr(result, "error", None):
            try:
                _did_auto_verify = await self._verify_and_fix(
                    engine, tools, result, on_tool, _on_narration, _on_permission)
                if _did_auto_verify:
                    # أعِد الحفظ لتضمين كتل الإصلاح ضمن الجلسة
                    try:
                        from core.action_blocks import serialize_block
                        _persist(response_text,
                                 [serialize_block(b) for b in (result.blocks or [])])
                    except Exception:
                        pass
            except Exception:
                _did_auto_verify = False

        # ── تذكير التحقق الذاتي: فقط إن كُتبت ملفات ولم يُتحقَّق (يدوياً أو تلقائياً) ─
        # (لا نُزعج المحادثات العادية بلا كتابة كود — تفادياً لتذكير بعد «هلا».)
        _verify_kw = ("✅ تم التحقق", "py_compile", "pytest", "الاختبارات تمر",
                      "tests pass", "✅ ok", "اختبار")
        _verified = any(s in (response_text or "").lower() for s in
                        (k.lower() for k in _verify_kw))
        if _wrote_code and not _verified and not _did_auto_verify:
            _rem = ("⚠️ تذكير: تحقّق من الملفات المُنشأة (py_compile/pytest) "
                    "قبل اعتبار المهمة منجزة.")
            await event_bus.emit(WeaverEvent(EventType.RESPONSE, _rem, _rem))

        await event_bus.emit(WeaverEvent(EventType.DONE, "اكتملت المهمة"))
        st.save_status("idle")

    async def _verify_and_fix(self, engine, tools, result,
                              on_tool, on_narration, on_permission) -> bool:
        """يتحقّق من الكود المكتوب (بنية py_compile + منطق pytest) ويُصلح الأخطاء
        تلقائياً عبر الوكيل، ثم يعيد الفحص — حلقة محدودة (WEAVER_AUTO_FIX_MAX).

        داخل الـ Sandbox إن كان مفعّلاً. يُرجع True إن جرى تحقّق. مُغلَّف بالكامل:
        أي عطل هنا لا يكسر المهمة. لا يُشغَّل شيء إلا عند WEAVER_AUTO_VERIFY=1.
        """
        from core.sandbox import verify_code, is_enabled as _sb_on
        where = " (داخل الـ Sandbox)" if _sb_on() else ""
        try:
            max_fix = int(os.environ.get("WEAVER_AUTO_FIX_MAX", "2"))
        except ValueError:
            max_fix = 2

        async def _emit(msg: str) -> None:
            await event_bus.emit(WeaverEvent(EventType.RESPONSE, str(msg)[:200], str(msg)))

        did = False
        for attempt in range(max_fix + 1):
            files = self._written_code_files(result)
            if not files:
                return did
            ok, summary, _kind = await verify_code(files, tools.work_dir)
            did = True
            if ok:
                await _emit(summary + where)
                return True
            # فشل الفحص
            if attempt >= max_fix:
                await _emit(f"⚠️ تعذّر الإصلاح التلقائي بعد {max_fix} محاولة — "
                            f"راجعه يدوياً:\n{summary}")
                return True
            await _emit(f"🔧 وجدتُ خطأً — أُصلحه تلقائياً "
                        f"(محاولة {attempt + 1}/{max_fix}){where}…")
            fix_prompt = (
                "الكود الذي كتبته للتوّ فيه خطأ يمنع صحّته. نتيجة الفحص:\n\n"
                + summary +
                "\n\nأصلح الخطأ مباشرةً في الملف/الملفات المذكورة (اقرأها بـ Read "
                "ثم عدّلها بـ Edit)، ثم توقّف. لا تشرح — فقط أصلح.")
            try:
                fix_res = await engine.run(
                    fix_prompt, on_tool=on_tool,
                    on_permission=on_permission, on_narration=on_narration)
            except Exception as exc:
                await _emit("تعذّر تشغيل الإصلاح التلقائي: " + str(exc))
                return True
            # ادمج كتل الإصلاح + الأدوات ليظهر في السجل ويُحفَظ
            try:
                for b in (getattr(fix_res, "blocks", None) or []):
                    result.blocks.append(b)
                if getattr(result, "tool_calls_made", None) is not None:
                    result.tool_calls_made.extend(getattr(fix_res, "tool_calls_made", None) or [])
            except Exception:
                pass
        return did

    _CODE_EXT = (".py", ".js", ".mjs", ".cjs", ".jsx")

    def _written_py_files(self, result) -> list:
        """ملفات بايثون التي كُتبت/عُدّلت (متوافق مع الاختبارات)."""
        return [p for p in self._written_code_files(result) if p.endswith(".py")]

    def _written_code_files(self, result) -> list:
        """يجمع مسارات ملفات الكود (بايثون/JS) التي كُتبت/عُدّلت — للتحقّق التلقائي."""
        seen, out = set(), []
        for b in (getattr(result, "blocks", None) or []):
            for op in (getattr(b, "ops", None) or []):
                if getattr(op, "tool_name", "") in ("Write", "Edit", "MultiEdit"):
                    p = str((getattr(op, "args", {}) or {}).get("path") or "")
                    if p.endswith(self._CODE_EXT) and p not in seen:
                        seen.add(p)
                        out.append(p)
        return out

    async def _auto_shot_result(self, tools, result, loop) -> None:
        """يلتقط تلقائياً لقطة شاشة حقيقية للناتج المرئي عند اكتمال المهمة.

        Auto-capture a real screenshot of a visual result (HTML/SVG file the
        task created/edited) and surface it in the completion card — as the
        user asked: «صورة لما عمله فعلاً» لا مجرد سجل commits. للمهام غير المرئية
        لا يُلتقط شيء (لا ضجيج). آمن تماماً: أي فشل يُتجاهَل بلا كسر للمهمة.
        """
        try:
            blocks = getattr(result, "blocks", None) or []
            visual_ext = (".html", ".htm", ".svg")
            target = ""
            for b in blocks:
                for op in getattr(b, "ops", []) or []:
                    if getattr(op, "tool_name", "") in ("Write", "Edit", "MultiEdit"):
                        p = str((getattr(op, "args", {}) or {}).get("path") or "")
                        if p.lower().endswith(visual_ext):
                            target = p   # آخر ملف مرئي كُتب = الناتج النهائي
            if not target:
                return
            await event_bus.emit(WeaverEvent(
                EventType.TOOL_START, "يلتقط لقطة للنتيجة", target))
            # subprocess حاجب → نفّذه في منفّذ منفصل كي لا يوقف حلقة الأحداث
            msg = await loop.run_in_executor(None, tools._screenshot, target)
            if "التقطت لقطة الشاشة" not in (msg or ""):
                return   # لا متصفّح Chromium أو فشل الالتقاط — تجاهل بهدوء
            from core.action_blocks import ActionBlock, ToolOp, serialize_ops
            blk = ActionBlock(ops=[ToolOp(
                tool_name="Screenshot", args={"target": target}, result=msg)])
            # (1) ألحِقه بكتل النتيجة ليُحفَظ في الجلسة (يظهر بعد إعادة التحميل أيضاً)
            try:
                if getattr(result, "blocks", None) is None:
                    result.blocks = []
                result.blocks.append(blk)
            except Exception:
                pass
            # (2) ابثّه حيّاً ليظهر في بطاقة الاكتمال فوراً (نفس شكل action_block)
            await event_bus.emit(WeaverEvent(
                EventType.ACTION_BLOCK, blk.summary_line(), blk._build_description(),
                diff_added=0, diff_removed=0, ops=serialize_ops(blk)))
        except Exception:
            pass

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
