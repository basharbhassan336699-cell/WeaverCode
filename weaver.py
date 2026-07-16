#!/usr/bin/env python3
"""
weaver.py — نقطة الدخول الرئيسية لـ WeaverCode
الاستخدام:
    python weaver.py "مهمتك هنا"
    python weaver.py --mode coding "راجع هذا الكود"
    python weaver.py --stream "اكتب سكربت Python"
    python weaver.py --interactive
"""

import asyncio
import argparse
import os
import sys
import json
import uuid
from pathlib import Path

# إضافة المشروع للمسار
sys.path.insert(0, str(Path(__file__).parent))

from core.engine.provider import get_provider
from core.engine.query_engine import QueryEngine
from core.tools.registry import ToolRegistry
from core.memory.store import MemoryStore
from core.commands import SlashCommands
from core.hooks import HookManager
from core.mcp import MCPManager
from prompts.system import get_system_prompt
from core.ui import (
    draw_welcome, draw_split_header, draw_tool_call,
    draw_response, draw_error, draw_success, draw_info,
    draw_stats, draw_prompt, draw_separator, clear_line,
    draw_permission_request, Spinner, ORANGE, GRAY, RESET, BOLD
)


# ── مفاتيح المعاينة لكل أداة عند طلب الصلاحية ────────────────────────────────
_PERMISSION_PREVIEW_KEYS = ("command", "cmd", "path", "file_path", "package",
                            "url", "message", "key", "value")


def _permission_preview(args: dict) -> str:
    """اختيار أهم وسيط لعرضه في طلب الصلاحية"""
    if not args:
        return ""
    for k in _PERMISSION_PREVIEW_KEYS:
        if k in args and args[k]:
            return str(args[k])
    return str(list(args.values())[0])


def make_plan_handler(spinner=None):
    """بناء دالة اعتماد الخطة التفاعلية. تُرجع True (اعتماد) أو False (رفض)."""
    def on_plan(plan_text):
        if spinner is not None:
            spinner.clear()
        print(f"\n{ORANGE}{'─' * 50}{RESET}")
        print(f"  {ORANGE}📋 الخطة المقترحة:{RESET}")
        print(f"{plan_text}")
        print(f"{ORANGE}{'─' * 50}{RESET}")
        if not sys.stdin.isatty():
            return False  # سياق غير تفاعلي → لا تعتمد تلقائياً
        try:
            choice = input(f"  {ORANGE}اعتماد الخطة والتنفيذ؟ [y/n]:{RESET} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return choice in ("y", "yes", "نعم", "ن")
    return on_plan


def make_permission_handler(spinner=None):
    """
    بناء دالة طلب الصلاحية التفاعلية.
    تُرجع "allow_once" | "allow_always" | "deny".
    """
    def on_permission(name, args):
        # لا تسأل أبداً في سياق غير تفاعلي (أنبوب/أتمتة) — الافتراض الآمن: رفض.
        # للأتمتة استخدم --yes أو WEAVER_AUTO_APPROVE=1.
        if not sys.stdin.isatty():
            return "deny"
        if spinner is not None:
            spinner.clear()
        draw_permission_request(name, _permission_preview(args))
        try:
            choice = input(f"  {ORANGE}اختيارك [y/a/n]:{RESET} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "deny"
        if choice in ("y", "yes", "نعم", "ن"):
            return "allow_once"
        if choice in ("a", "always", "دائم", "د"):
            return "allow_always"
        return "deny"
    return on_permission


def load_env():
    """تحميل متغيرات البيئة من config/.env تلقائياً إن وُجد.

    لا يستبدل المتغيرات المضبوطة مسبقاً (setdefault) حتى تبقى الأولوية
    لأوامر سطر الأوامر ومتغيرات البيئة الحقيقية.
    """
    env_file = Path(__file__).parent / "config" / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        # يدعم صيغة "export KEY=VALUE"
        if line.startswith("export "):
            line = line[len("export "):].strip()
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip()
        # إزالة علامات الاقتباس المحيطة إن وُجدت
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
            val = val[1:-1]
        if key:
            os.environ.setdefault(key, val)


async def build_engine(mode: str = "main", plan_mode: bool = False):
    """
    تهيئة كاملة للمحرّك: المزوّد + الأدوات + الذاكرة + hooks + خوادم MCP.
    يُرجع (engine, provider, mcp) — على المتصل استدعاء mcp.stop_all() في النهاية.
    """
    provider = get_provider()
    memory = MemoryStore()
    tools = ToolRegistry()
    hooks = HookManager()

    # hook: InstructionsLoaded — عند تحميل CLAUDE.md في بداية الجلسة
    claude_md = Path(__file__).parent / "CLAUDE.md"
    if claude_md.exists():
        try:
            hooks.run_instructions_loaded(str(claude_md))
        except Exception:
            pass

    # تشغيل خوادم MCP (إن وُجد config/mcp.json) وتسجيل أدواتها
    mcp = MCPManager()
    try:
        registered = await mcp.start_all(tools)
        if registered:
            draw_info(f"MCP: {len(registered)} أداة خارجية مُحمّلة")
    except Exception:
        pass

    engine = QueryEngine(
        provider=provider,
        tool_registry=tools,
        memory=memory,
        system_prompt=get_system_prompt(mode),
        hooks=hooks if hooks.has_any() else None,
        plan_mode=plan_mode,
    )
    return engine, provider, mcp


async def run_once(prompt: str, mode: str = "main", stream: bool = False,
                   plan_mode: bool = False):
    """تشغيل مهمة واحدة"""
    load_env()

    engine, provider, mcp = await build_engine(mode, plan_mode=plan_mode)

    draw_welcome(provider.config.model, provider.config.base_url)
    draw_split_header(provider.config.model,
                      provider.config.base_url.split("//")[-1].split("/")[0])

    spinner = Spinner("يعالج...")

    def on_tool(name, args):
        spinner.clear()
        key_arg = str(list(args.values())[0]) if args else ""
        draw_tool_call(name, key_arg)

    on_permission = make_permission_handler(spinner)
    on_plan = make_plan_handler(spinner)

    if stream:
        print(f"\n{ORANGE}🕸️{RESET}  ", end="", flush=True)
        async for chunk in engine.stream_run(prompt, on_tool=on_tool,
                                             on_permission=on_permission):
            print(chunk, end="", flush=True)
        print("\n")
        await mcp.stop_all()
    else:
        spinner.start()
        try:
            result = await engine.run(prompt, on_tool=on_tool,
                                      on_permission=on_permission, on_plan=on_plan)
        finally:
            await spinner.stop()

        if result.error:
            draw_error(result.error)
        elif not (result.text or "").strip():
            _show_empty_diagnostic(provider)
        else:
            draw_response(result.text)
            if result.tool_calls_made:
                draw_stats(result.turns, result.tool_calls_made)

        await mcp.stop_all()

    await provider.close()


def _show_empty_diagnostic(provider) -> None:
    """عند رجوع نصّ فارغ: اعرض الاستجابة الخام من المزوّد بدل الصمت."""
    raw = (getattr(provider, "last_raw", "") or "").strip()
    draw_error("النموذج أرجع رداً فارغاً.")
    if raw:
        print(f"{GRAY}🔎 آخر استجابة خام من المزوّد (شخّص بها الشكل):{RESET}")
        print(raw[:1200])
        print(f"{GRAY}شغّل الفاحص لمعرفة الصيغة الصحيحة:  "
              f"bash scripts/weaver-doctor.sh{RESET}")
    else:
        print(f"{GRAY}لم تُلتقط استجابة خام. شغّل:  "
              f"bash scripts/weaver-doctor.sh{RESET}")


def _load_models(current: str = "") -> list:
    """تحميل قائمة النماذج من config/models.json + ضمان وجود النموذج الحالي."""
    models = []
    path = Path(__file__).parent / "config" / "models.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            models = [m for m in data.get("models", []) if m.get("name")]
        except Exception:
            models = []
    if current and not any(m["name"] == current for m in models):
        models.insert(0, {"name": current, "desc": "النموذج الحالي"})
    return models


def _pick_model_numbered(current: str, models: list):
    """اختيار نموذج بقائمة مرقّمة (يعمل في أي طرفية)."""
    print(f"\n{ORANGE}اختر النموذج:{RESET}")
    for i, m in enumerate(models, 1):
        mark = f" {ORANGE}✓{RESET}" if m["name"] == current else ""
        print(f"  {ORANGE}{i:>2}.{RESET} {m['name']}{mark}   {GRAY}{m.get('desc','')}{RESET}")
    print(f"  {GRAY}(اكتب رقماً أو اسم نموذج مخصّص · Enter للإبقاء){RESET}")
    try:
        c = input(f"  {ORANGE}اختيارك:{RESET} ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not c:
        return None
    if c.isdigit() and 1 <= int(c) <= len(models):
        return models[int(c) - 1]["name"]
    return c  # اسم مخصّص


async def _pick_model(current: str):
    """قائمة نماذج تفاعلية (أسهم + Enter) عبر prompt_toolkit، وإلا قائمة مرقّمة."""
    models = _load_models(current)
    if not models:
        return None
    try:
        from prompt_toolkit.shortcuts import radiolist_dialog
    except Exception:
        return _pick_model_numbered(current, models)
    values = [(m["name"], f"{m['name']}   —   {m.get('desc','')}") for m in models]
    try:
        return await radiolist_dialog(
            title="اختر النموذج",
            text="النماذج المتاحة (↑↓ للتنقّل · Enter للتأكيد · Esc للإلغاء):",
            values=values, default=current,
        ).run_async()
    except Exception:
        return _pick_model_numbered(current, models)


def _show_mcp_status(mcp):
    """عرض حالة خوادم MCP (مثل /mcp في الأدوات المشابهة)."""
    servers = getattr(mcp, "servers", {}) or {}
    cfg = Path(__file__).parent / "config" / "mcp.json"
    if servers:
        draw_info(f"خوادم MCP النشطة ({len(servers)}):")
        for name, srv in servers.items():
            tools = len(getattr(srv, "tools", []) or [])
            print(f"  {ORANGE}•{RESET} {name}  {GRAY}({tools} أداة){RESET}")
    else:
        draw_info("لا توجد خوادم MCP مُهيّأة.")
        print(f"  {GRAY}أضف خوادم في config/mcp.json (يدعم stdio/sse/http). "
              f"مثال في التوثيق. مسار الإعداد: {cfg}{RESET}")


# ── أوامر مدمجة تفاعلية تظهر في الإكمال التلقائي ──
_BUILTIN_CMDS = [
    {"name": "model", "description": "اختيار النموذج من قائمة تفاعلية"},
    {"name": "mcp", "description": "عرض حالة خوادم MCP"},
    {"name": "mode", "description": "تبديل وضع الوكيل (coding/project/...)"},
    {"name": "plan", "description": "تفعيل/إيقاف وضع التخطيط"},
    {"name": "stats", "description": "إحصاءات الذاكرة"},
    {"name": "commands", "description": "عرض كل أوامر السلاش"},
]


def _make_slash_prompt(commands):
    """بناء جلسة إدخال مع إكمال تلقائي لأوامر السلاش (يظهر عند كتابة '/').

    يستخدم prompt_toolkit إن كان مثبّتاً؛ وإلا يُرجع None فنسقط لـ input() العادي.
    للتفعيل على Termux:  pip install prompt_toolkit --break-system-packages
    """
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.completion import Completer, Completion
        from prompt_toolkit.shortcuts import CompleteStyle
    except Exception:
        return None

    metas = _BUILTIN_CMDS + commands.list_meta()

    class _SlashCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor
            # نُظهر القائمة فقط أثناء كتابة اسم الأمر (يبدأ بـ / وبلا مسافة)
            if not text.startswith("/") or " " in text:
                return
            q = text[1:].lower()
            for m in metas:
                if q in m["name"].lower():
                    yield Completion(
                        "/" + m["name"], start_position=-len(text),
                        display="/" + m["name"],
                        display_meta=(m.get("description") or "")[:60],
                    )

    try:
        return PromptSession(
            completer=_SlashCompleter(),
            complete_while_typing=True,       # تظهر أثناء الكتابة
            reserve_space_for_menu=8,         # يحجز مساحة للقائمة (مهم لظهورها)
            complete_style=CompleteStyle.COLUMN,  # سطر لكل أمر + وصفه
            mouse_support=True,               # اللمس لاختيار أمر (Termux)
        )
    except Exception:
        # نسخ قديمة قد لا تدعم بعض الوسائط → أنشئ جلسة أبسط
        try:
            return PromptSession(completer=_SlashCompleter(),
                                 complete_while_typing=True,
                                 reserve_space_for_menu=8)
        except Exception:
            return None


async def interactive_mode(initial_history=None, session_id=None,
                           session_name=None):
    """وضع المحادثة التفاعلية.

    يدعم استئناف جلسة سابقة (initial_history) ويحفظ الجلسة تلقائياً بعد كل رد
    حتى يمكن استئنافها لاحقاً عبر --resume.
    """
    load_env()

    engine, provider, mcp = await build_engine("main")
    commands = SlashCommands()

    draw_welcome(provider.config.model, provider.config.base_url)
    print(f"{GRAY}اكتب 'خروج' للإنهاء | '/model' اختيار النموذج | '/mcp' حالة MCP | "
          f"'/mode <mode>' | '/plan' التخطيط | '/' لكل الأوامر{RESET}")
    draw_separator()

    from core.engine.provider import Message
    history = list(initial_history) if initial_history else []
    session_id = session_id or uuid.uuid4().hex[:8]

    def _save_session(last_prompt: str):
        """حفظ الجلسة الحالية في الذاكرة (تلقائياً بعد كل رد)."""
        try:
            msgs = [{"role": m.role, "content": m.content} for m in history
                    if m.role in ("user", "assistant")]
            name = session_name or last_prompt[:40] or session_id
            engine.memory.save_session(session_id, name, last_prompt,
                                       json.dumps(msgs, ensure_ascii=False))
        except Exception:
            pass

    # جلسة إدخال مع إكمال أوامر السلاش (إن توفّر prompt_toolkit)
    slash_session = _make_slash_prompt(commands)
    if slash_session is not None:
        draw_info("الإكمال التلقائي للأوامر مُفعّل — اكتب '/' لعرض القائمة.")

    while True:
        try:
            if slash_session is not None:
                prompt = (await slash_session.prompt_async("❯ أنت: ")).strip()
            else:
                prompt = draw_prompt()
        except (EOFError, KeyboardInterrupt):
            print(f"\n\n{ORANGE}🕸️  إلى اللقاء!{RESET}")
            break

        if not prompt:
            continue

        if prompt.lower() in ("خروج", "exit", "quit"):
            print(f"{ORANGE}🕸️  إلى اللقاء!{RESET}")
            break

        if prompt.startswith("/mode "):
            mode = prompt[6:].strip()
            engine.system_prompt = get_system_prompt(mode)
            draw_success(f"الوضع: {mode}")
            continue

        if prompt.startswith("/model "):
            model = prompt[7:].strip()
            provider.config.model = model
            os.environ["WEAVER_MODEL"] = model
            draw_success(f"النموذج: {model}")
            continue

        if prompt.strip() == "/model":
            chosen = await _pick_model(provider.config.model)
            if chosen and chosen != provider.config.model:
                provider.config.model = chosen
                os.environ["WEAVER_MODEL"] = chosen
                draw_success(f"النموذج: {chosen}")
            else:
                draw_info(f"أُبقي النموذج: {provider.config.model}")
            continue

        if prompt.strip() == "/mcp":
            _show_mcp_status(mcp)
            continue

        if prompt.startswith("/stats"):
            stats = engine.memory.get_stats()
            draw_info(f"محادثات محفوظة: {stats['conversations']} | حقائق: {stats['facts']}")
            continue

        if prompt.strip() in ("/commands", "/help"):
            names = commands.names()
            draw_info("أوامر السلاش المتاحة: " + ", ".join("/" + n for n in names))
            continue

        if prompt.strip() in ("/plan", "/plan on"):
            engine.plan_mode = True
            draw_success("وضع التخطيط مُفعّل — سأخطّط قبل التنفيذ حتى تعتمد الخطة.")
            continue
        if prompt.strip() == "/plan off":
            engine.plan_mode = False
            draw_success("وضع التخطيط مُعطّل.")
            continue

        # ── أوامر السلاش من .claude/commands/ ────────────────────────────────
        parsed = commands.parse(prompt)
        if parsed:
            cmd_name, cmd_args = parsed
            rendered = commands.render(cmd_name, cmd_args)
            if rendered:
                draw_info(f"تشغيل الأمر /{cmd_name}")
                prompt = rendered  # نشغّل قالب الأمر كبروموه
            else:
                draw_error(f"تعذّر تحميل الأمر /{cmd_name}")
                continue

        spinner = Spinner("يعالج...")

        def on_tool(name, args):
            spinner.clear()
            key_arg = str(list(args.values())[0]) if args else ""
            draw_tool_call(name, key_arg)

        on_permission = make_permission_handler(spinner)
        on_plan = make_plan_handler(spinner)

        spinner.start()
        try:
            result = await engine.run(prompt, history=history, on_tool=on_tool,
                                      on_permission=on_permission, on_plan=on_plan)
        finally:
            await spinner.stop()

        if result.error:
            draw_error(result.error)
        elif not (result.text or "").strip():
            _show_empty_diagnostic(provider)
        else:
            draw_response(result.text)
            if result.tool_calls_made:
                draw_stats(result.turns, result.tool_calls_made)
            # تراكم السجل + حفظ الجلسة تلقائياً للاستئناف لاحقاً
            history.append(Message(role="user", content=prompt))
            history.append(Message(role="assistant", content=result.text))
            _save_session(prompt)

    await mcp.stop_all()
    await provider.close()


async def _show_sessions():
    """عرض الجلسات المحفوظة (لأمر --sessions)."""
    import datetime
    from core.memory.store import MemoryStore
    sessions = MemoryStore().list_sessions()
    if not sessions:
        draw_info("لا توجد جلسات محفوظة بعد.")
        return
    print(f"\n{ORANGE}الجلسات المحفوظة:{RESET}")
    for i, s in enumerate(sessions, 1):
        dt = datetime.datetime.fromtimestamp(
            s["updated_at"]).strftime("%Y-%m-%d %H:%M")
        name = s["name"] or s["id"][:8]
        prompt = (s["last_prompt"] or "")[:60]
        print(f"  {ORANGE}{i}.{RESET} [{name}] {GRAY}{dt}{RESET} — {prompt}")
    print(f"\n{GRAY}للاستئناف: python weaver.py --resume <الاسم أو ID>{RESET}")


async def resume_session(session_ref=None):
    """اختيار جلسة سابقة أو استئنافها مباشرة."""
    load_env()
    from core.memory.store import MemoryStore
    from core.engine.provider import Message
    memory = MemoryStore()

    if session_ref is None or session_ref == "__picker__":
        sessions = memory.list_sessions()
        if not sessions:
            draw_error("لا توجد جلسات محفوظة.")
            return
        import datetime
        print(f"\n{ORANGE}الجلسات المحفوظة:{RESET}")
        for i, s in enumerate(sessions, 1):
            dt = datetime.datetime.fromtimestamp(
                s["updated_at"]).strftime("%Y-%m-%d %H:%M")
            name = s["name"] or s["id"][:8]
            prompt = (s["last_prompt"] or "")[:60]
            print(f"  {ORANGE}{i}.{RESET} [{name}] {GRAY}{dt}{RESET} — {prompt}")
        print()
        try:
            choice = input(f"  {ORANGE}اختر رقماً أو اكتب ID/اسم الجلسة:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if choice.isdigit() and 1 <= int(choice) <= len(sessions):
            session_ref = sessions[int(choice) - 1]["id"]
        else:
            session_ref = choice

    data = memory.load_session(session_ref)
    if not data:
        draw_error(f"لم يُعثر على جلسة: {session_ref}")
        return

    draw_success(f"استئناف الجلسة: {data.get('name') or data['id'][:8]}")
    history = []
    for m in data.get("messages", []):
        if m.get("role") in ("user", "assistant") and m.get("content"):
            history.append(Message(role=m["role"], content=m["content"]))

    await interactive_mode(initial_history=history,
                           session_id=data["id"],
                           session_name=data.get("name"))


def main():
    parser = argparse.ArgumentParser(
        description="WeaverCode — وكيل برمجي مستقل",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
أمثلة:
  python weaver.py "اقرأ ملف README.md"
  python weaver.py --mode coding "راجع كود provider.py"
  python weaver.py --stream "اشرح بنية المشروع"
  python weaver.py --interactive
  python weaver.py --model "gpt-4o" "مهمتك"
        """,
    )
    parser.add_argument("prompt", nargs="?", help="المهمة المطلوبة")
    parser.add_argument("--mode", default="main",
                        choices=["main", "coding", "project", "security", "autonomous", "analysis"],
                        help="وضع عمل الوكيل")
    parser.add_argument("--stream", action="store_true", help="وضع التدفق")
    parser.add_argument("--plan", action="store_true",
                        help="وضع التخطيط: يخطّط ويستأذنك قبل تنفيذ أي تعديل")
    parser.add_argument("--interactive", "-i", action="store_true", help="وضع المحادثة التفاعلية")
    parser.add_argument("--background", "--bg", "-b", action="store_true",
                        help="تشغيل لوحة الويب + الخلفية (http://localhost:8080)")
    parser.add_argument("--web", "-w", action="store_true",
                        help="تشغيل لوحة الويب في المقدّمة فقط")
    parser.add_argument("--daemon", action="store_true",
                        help="تشغيل الـ daemon (الخلفية) بلا واجهة ويب")
    parser.add_argument("--model", help="اسم النموذج (يتجاوز WEAVER_MODEL)")
    parser.add_argument("--key", help="مفتاح API (يتجاوز WEAVER_API_KEY)")
    parser.add_argument("--url", help="عنوان API (يتجاوز WEAVER_BASE_URL)")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="الموافقة التلقائية على كل الأدوات دون سؤال (احذر)")
    parser.add_argument("--version", "-v", action="store_true",
                        help="عرض إصدار WeaverCode والخروج")
    parser.add_argument("--print-system", action="store_true",
                        help="طباعة البروموه النظامي الفعلي المُرسَل للنموذج (تشخيص الهوية)")
    parser.add_argument("--resume", "-r", nargs="?", const="__picker__",
                        metavar="SESSION",
                        help="استئناف جلسة سابقة (بدون قيمة = اختيار تفاعلي)")
    parser.add_argument("--rename", metavar="NAME",
                        help="تسمية الجلسة الحالية عند بدء وضع تفاعلي جديد")
    parser.add_argument("--sessions", action="store_true",
                        help="عرض قائمة الجلسات المحفوظة")

    args = parser.parse_args()

    # تحميل .env تلقائياً عند بدء التشغيل (قبل تطبيق أوامر سطر الأوامر)
    load_env()

    # تطبيق الإعدادات من الأوامر
    if args.model:
        os.environ["WEAVER_MODEL"] = args.model
    if args.key:
        os.environ["WEAVER_API_KEY"] = args.key
    if args.url:
        os.environ["WEAVER_BASE_URL"] = args.url
    if args.yes:
        os.environ["WEAVER_AUTO_APPROVE"] = "1"

    # ── تشخيص: عرض الإصدار ──────────────────────────────────────────────────
    if args.version:
        from core.ui import WEAVER_VERSION, get_version
        guard = "مفعّل" if os.environ.get("WEAVER_IDENTITY_GUARD", "1").lower() \
            not in ("0", "false", "off", "no") else "معطّل"
        print(f"🕸️  WeaverCode {get_version()} (base {WEAVER_VERSION})")
        print(f"    النموذج:  {os.environ.get('WEAVER_MODEL', 'غير محدد')}")
        print(f"    المزود:   {os.environ.get('WEAVER_BASE_URL', 'غير محدد')}")
        print(f"    حارس الهوية: {guard}")
        auto = os.environ.get("WEAVER_AUTO_APPROVE", "0").lower() in ("1", "true", "yes", "on", "نعم")
        print(f"    الصلاحيات: {'موافقة تلقائية (بلا سؤال)' if auto else 'تسأل قبل الأدوات الخطرة'}")
        return

    # ── تشخيص: طباعة البروموه النظامي الفعلي ────────────────────────────────
    if args.print_system:
        system = get_system_prompt(args.mode)
        print("=" * 60)
        print(f"البروموه النظامي الفعلي للوضع '{args.mode}' (يُرسَل للنموذج):")
        print("=" * 60)
        print(system)
        print("=" * 60)
        print("ملاحظة: يُضاف أيضاً تذكير هوية إلى نص المستخدم نفسه (حارس الهوية).")
        return

    if args.plan:
        os.environ["WEAVER_PLAN_MODE"] = "1"

    # ── أوضاع الويب/الخلفية ─────────────────────────────────────────────────
    if args.background:
        script = Path(__file__).parent / "scripts" / "weaver-bg.sh"
        os.system(f"bash '{script}'")
        return
    if args.web:
        from web.server import main as web_main
        web_main()
        return
    if args.daemon:
        from background.daemon import daemon_main
        asyncio.run(daemon_main())
        return

    # ── الجلسات: العرض والاستئناف ───────────────────────────────────────────
    if args.sessions:
        asyncio.run(_show_sessions())
        return
    if args.resume is not None:
        asyncio.run(resume_session(
            None if args.resume == "__picker__" else args.resume))
        return

    if args.interactive:
        asyncio.run(interactive_mode(session_name=args.rename))
    elif args.prompt:
        asyncio.run(run_once(args.prompt, mode=args.mode, stream=args.stream,
                             plan_mode=args.plan))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
