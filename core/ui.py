"""
ui.py — واجهة سطر الأوامر لـ WeaverCode مع الأيقونة والألوان
"""

import os
import sys
from pathlib import Path

# ── الألوان الرسمية لـ WeaverCode ────────────────────────────────────────────
ORANGE = "\033[38;2;198;113;33m"    # #C67121 — برتقالي الشبكة
DARK   = "\033[38;2;180;100;20m"    # برتقالي داكن
WHITE  = "\033[97m"
GRAY   = "\033[90m"
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

# ── أيقونة ASCII للـ terminal ────────────────────────────────────────────────
WEAVER_ASCII = f"""{ORANGE}
    ╭──────────────────────────────────╮
    │  {BOLD}🕸️  W E A V E R C O D E{RESET}{ORANGE}        │
    │  {GRAY}وكيل برمجي مستقل{ORANGE}               │
    ╰──────────────────────────────────╯{RESET}"""

WEAVER_MINI = f"{ORANGE}🕸️  {BOLD}WeaverCode{RESET}"

# ── شبكة ASCII صغيرة ─────────────────────────────────────────────────────────
WEB_SMALL = f"""{ORANGE}
      *  ·  ·  *  ·  ·  *
    · ╲  ·  · ╱ ╲  ·  · ╱ ·
    ·  ╲·····╱   ╲·····╱  ·
    * ··╲···╱·····╲···╱·· *
    ·    ╲·╱·······╲·╱    ·
    ·  ···X·····────X···  ·
    ·    ╱·╲·······╱·╲    ·
    * ··╱···╲·····╱···╲·· *
    ·  ╱·····╲   ╱·····╲  ·
    · ╱  ·  · ╲ ╱  ·  · ╲ ·
      *  ·  ·  *  ·  ·  *{RESET}"""


def get_icon_path(name: str = "icon_internal_256.png") -> Path:
    """مسار الأيقونة في مجلد assets"""
    here = Path(__file__).parent
    return here / "assets" / name


def show_banner(model: str = "", provider_url: str = ""):
    """عرض البانر عند بدء WeaverCode"""
    print(WEAVER_ASCII)
    if model:
        print(f"  {GRAY}النموذج:{RESET} {ORANGE}{model}{RESET}")
    if provider_url:
        domain = provider_url.split("//")[-1].split("/")[0]
        print(f"  {GRAY}المزود: {RESET}{GRAY}{domain}{RESET}")
    print(f"  {GRAY}{'─' * 36}{RESET}\n")


def show_mini_banner():
    """بانر مضغوط للوضع التفاعلي"""
    print(f"\n{WEAVER_MINI} {GRAY}| اكتب 'خروج' للإنهاء{RESET}")


def format_tool_call(name: str, arg: str = "") -> str:
    """تنسيق استدعاء الأداة"""
    arg_str = f"({arg[:50]})" if arg else ""
    return f"  {ORANGE}🔧 {name}{GRAY}{arg_str}{RESET}"


def format_response(text: str) -> str:
    """تنسيق رد الوكيل"""
    return f"\n{ORANGE}🕸️{RESET}  {text}"


def format_error(text: str) -> str:
    return f"\n{DARK}❌ {text}{RESET}"


def format_success(text: str) -> str:
    return f"{ORANGE}✅ {text}{RESET}"


def format_info(text: str) -> str:
    return f"{GRAY}ℹ️  {text}{RESET}"


def spinner_frames():
    """إطارات الـ spinner بشكل شبكة"""
    return ["🕸️ ", "🕷️ ", "🕸️ ", "  "]


def print_stats(turns: int, tools: list, cost_info: str = ""):
    """طباعة إحصاءات الجلسة"""
    if tools:
        tools_str = ", ".join(set(tools))
        print(f"\n{GRAY}📊 {turns} دورة | الأدوات: {tools_str}{RESET}")
    if cost_info:
        print(f"{GRAY}💰 {cost_info}{RESET}")


def clear_line():
    """مسح السطر الحالي"""
    print("\r\033[K", end="", flush=True)


def icon_exists() -> bool:
    """هل الأيقونة موجودة؟"""
    return get_icon_path().exists()


# ── دعم Kitty / iTerm2 لعرض الصور في الـ terminal ───────────────────────────

def try_show_terminal_image(path: Path, width: int = 64) -> bool:
    """
    محاولة عرض الأيقونة في الـ terminal إذا كان يدعم ذلك
    يدعم: Kitty terminal protocol
    """
    if not path.exists():
        return False

    # فحص Kitty
    if os.environ.get("TERM") == "xterm-kitty":
        try:
            import base64
            data = path.read_bytes()
            b64 = base64.standard_b64encode(data).decode()
            # Kitty graphics protocol
            chunk_size = 4096
            chunks = [b64[i:i+chunk_size] for i in range(0, len(b64), chunk_size)]
            for i, chunk in enumerate(chunks):
                m = 1 if i < len(chunks) - 1 else 0
                if i == 0:
                    sys.stdout.write(
                        f"\033_Ga=T,f=100,m={m},c={width},r=8;"
                        f"{chunk}\033\\"
                    )
                else:
                    sys.stdout.write(f"\033_Gm={m};{chunk}\033\\")
            sys.stdout.write("\n")
            sys.stdout.flush()
            return True
        except Exception:
            pass

    return False


def show_startup_icon():
    """عرض الأيقونة عند البدء"""
    icon = get_icon_path("icon_internal_64.png")
    if not try_show_terminal_image(icon, width=8):
        # fallback: ASCII
        pass  # البانر النصي يكفي
