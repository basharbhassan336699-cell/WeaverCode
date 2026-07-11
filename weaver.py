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
from pathlib import Path

# إضافة المشروع للمسار
sys.path.insert(0, str(Path(__file__).parent))

from core.engine.provider import get_provider
from core.engine.query_engine import QueryEngine
from core.tools.registry import ToolRegistry
from core.memory.store import MemoryStore
from prompts.system import get_system_prompt
from core.ui import (
    draw_welcome, draw_split_header, draw_tool_call,
    draw_response, draw_error, draw_success, draw_info,
    draw_stats, draw_prompt, draw_separator, clear_line,
    Spinner, ORANGE, GRAY, RESET, BOLD
)


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


async def run_once(prompt: str, mode: str = "main", stream: bool = False):
    """تشغيل مهمة واحدة"""
    load_env()

    provider = get_provider()
    memory = MemoryStore()
    tools = ToolRegistry()
    system = get_system_prompt(mode)

    engine = QueryEngine(
        provider=provider,
        tool_registry=tools,
        memory=memory,
        system_prompt=system,
    )

    draw_welcome(provider.config.model, provider.config.base_url)
    draw_split_header(provider.config.model,
                      provider.config.base_url.split("//")[-1].split("/")[0])

    if stream:
        print(f"\n{ORANGE}🕸️{RESET}  ", end="", flush=True)
        async for chunk in engine.stream_run(prompt):
            print(chunk, end="", flush=True)
        print("\n")
    else:
        spinner = Spinner("يعالج...")

        def on_tool(name, args):
            spinner.clear()
            key_arg = str(list(args.values())[0]) if args else ""
            draw_tool_call(name, key_arg)

        spinner.start()
        try:
            result = await engine.run(prompt, on_tool=on_tool)
        finally:
            await spinner.stop()

        if result.error:
            draw_error(result.error)
        else:
            draw_response(result.text)
            if result.tool_calls_made:
                draw_stats(result.turns, result.tool_calls_made)

    await provider.close()


async def interactive_mode():
    """وضع المحادثة التفاعلية"""
    load_env()

    provider = get_provider()
    memory = MemoryStore()
    tools = ToolRegistry()
    engine = QueryEngine(
        provider=provider,
        tool_registry=tools,
        memory=memory,
        system_prompt=get_system_prompt("main"),
    )

    draw_welcome(provider.config.model, provider.config.base_url)
    print(f"{GRAY}اكتب 'خروج' للإنهاء | '/mode <mode>' لتغيير الوضع | '/model <name>' لتبديل النموذج{RESET}")
    draw_separator()

    history = []

    while True:
        try:
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
            draw_success(f"النموذج: {model}")
            continue

        if prompt.startswith("/stats"):
            stats = engine.memory.get_stats()
            draw_info(f"محادثات محفوظة: {stats['conversations']} | حقائق: {stats['facts']}")
            continue

        spinner = Spinner("يعالج...")

        def on_tool(name, args):
            spinner.clear()
            key_arg = str(list(args.values())[0]) if args else ""
            draw_tool_call(name, key_arg)

        spinner.start()
        try:
            result = await engine.run(prompt, history=history, on_tool=on_tool)
        finally:
            await spinner.stop()

        if result.error:
            draw_error(result.error)
        else:
            draw_response(result.text)
            if result.tool_calls_made:
                draw_stats(result.turns, result.tool_calls_made)

    await provider.close()


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
    parser.add_argument("--interactive", "-i", action="store_true", help="وضع المحادثة التفاعلية")
    parser.add_argument("--model", help="اسم النموذج (يتجاوز WEAVER_MODEL)")
    parser.add_argument("--key", help="مفتاح API (يتجاوز WEAVER_API_KEY)")
    parser.add_argument("--url", help="عنوان API (يتجاوز WEAVER_BASE_URL)")
    parser.add_argument("--version", "-v", action="store_true",
                        help="عرض إصدار WeaverCode والخروج")
    parser.add_argument("--print-system", action="store_true",
                        help="طباعة البروموه النظامي الفعلي المُرسَل للنموذج (تشخيص الهوية)")

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

    # ── تشخيص: عرض الإصدار ──────────────────────────────────────────────────
    if args.version:
        from core.ui import WEAVER_VERSION, get_version
        guard = "مفعّل" if os.environ.get("WEAVER_IDENTITY_GUARD", "1").lower() \
            not in ("0", "false", "off", "no") else "معطّل"
        print(f"🕸️  WeaverCode {get_version()} (base {WEAVER_VERSION})")
        print(f"    النموذج:  {os.environ.get('WEAVER_MODEL', 'غير محدد')}")
        print(f"    المزود:   {os.environ.get('WEAVER_BASE_URL', 'غير محدد')}")
        print(f"    حارس الهوية: {guard}")
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

    if args.interactive:
        asyncio.run(interactive_mode())
    elif args.prompt:
        asyncio.run(run_once(args.prompt, mode=args.mode, stream=args.stream))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
