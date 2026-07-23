#!/usr/bin/env python3
"""
ui.py — واجهة WeaverCode الاحترافية للـ terminal
================================================

واجهة استقبال ولوحة حالة مستوحاة من مستوى Claude Code v2 ومُكيَّفة بالكامل
لهوية WeaverCode البصرية.

الألوان الرسمية:
    #C67121 برتقالي الشبكة | #0A0805 خلفية داكنة جداً

تُوفّر:
    - draw_welcome()        شاشة الاستقبال بعمودين + عنكبوت ASCII
    - draw_split_header()   رأس الشاشة المنقسمة أثناء العمل
    - draw_tool_call()      عرض استدعاء أداة
    - draw_response()       عرض رد الوكيل
    - draw_thinking()       مؤشر تفكير متحرك 🕸️/🕷️
    - draw_stats()          إحصاءات بعد الرد
    - Spinner               مؤشر تفكير غير متزامن يعمل أثناء الانتظار

كما تحافظ على أسماء الدوال القديمة (show_banner, format_response, ...)
للتوافق الرجعي مع أي كود يعتمدها.
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

# ── الألوان الرسمية لـ WeaverCode ─────────────────────────────────────────
OR  = "\033[38;2;198;113;33m"   # #C67121 برتقالي الشبكة
OR2 = "\033[38;2;230;140;50m"   # برتقالي فاتح #E68C32
DRK = "\033[38;2;120;65;10m"    # برتقالي داكن
WHT = "\033[97m"
GRY = "\033[90m"
GR2 = "\033[37m"
GRN = "\033[38;2;80;200;80m"
RED = "\033[91m"
CYN = "\033[38;2;100;200;220m"
RST = "\033[0m"
BLD = "\033[1m"
DIM = "\033[2m"

# ── أسماء متوافقة رجعياً (كانت مستخدمة في النسخة السابقة) ──────────────────
ORANGE = OR
DARK   = DRK
WHITE  = WHT
GRAY   = GRY
RESET  = RST
BOLD   = BLD

WEAVER_VERSION = "v4.16.0"

# قائمة كل رموز الـ ANSI لإزالتها عند حساب العرض الحقيقي
_ANSI = [OR, OR2, DRK, WHT, GRY, GR2, GRN, RED, CYN, RST, BLD, DIM,
         ORANGE, DARK, WHITE, GRAY, RESET, BOLD]


# ── أدوات مساعدة عامة ──────────────────────────────────────────────────────

def _is_tty() -> bool:
    """هل المخرج طرفية تفاعلية؟ (لتفادي مسح الشاشة عند التمرير عبر أنبوب)"""
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def cls():
    """مسح الشاشة — فقط في الطرفية التفاعلية"""
    if _is_tty():
        os.system("clear")


def term_width() -> int:
    return shutil.get_terminal_size((80, 24)).columns


def term_height() -> int:
    return shutil.get_terminal_size((80, 24)).lines


def _visible_len(text: str) -> int:
    """طول النص الظاهر بعد إزالة رموز ANSI"""
    clean = text
    for esc in _ANSI:
        clean = clean.replace(esc, "")
    return len(clean)


def clear_line():
    """مسح السطر الحالي وإرجاع المؤشر لبدايته"""
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


# ── مصادر البيانات (الإعدادات + الذاكرة) ──────────────────────────────────

def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _db_path() -> Path:
    raw = os.environ.get("WEAVER_DB_PATH", "~/.weaver/memory.db")
    return Path(os.path.expanduser(raw))


def get_env_info() -> dict:
    """
    قراءة الإعدادات الحالية.
    الأولوية لمتغيرات البيئة (يحمّلها weaver.py من .env)، ثم ملف config/.env.
    """
    info = {"model": "غير محدد", "provider": "غير محدد",
            "key_set": False, "key_preview": "···"}

    model = os.environ.get("WEAVER_MODEL")
    url = os.environ.get("WEAVER_BASE_URL")
    key = os.environ.get("WEAVER_API_KEY")

    # احتياطي: قراءة الملف مباشرةً إن لم تُضبط البيئة بعد
    if not (model and url and key):
        env_file = _project_root() / "config" / ".env"
        try:
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("WEAVER_MODEL=") and not model:
                    model = line.split("=", 1)[1].strip()
                elif line.startswith("WEAVER_BASE_URL=") and not url:
                    url = line.split("=", 1)[1].strip()
                elif line.startswith("WEAVER_API_KEY=") and not key:
                    key = line.split("=", 1)[1].strip()
        except Exception:
            pass

    if model:
        info["model"] = model
    if url:
        info["provider"] = url.split("//")[-1].split("/")[0]
    if key and len(key) > 5 and "YOUR_" not in key.upper():
        info["key_set"] = True
        info["key_preview"] = key[:8] + "···"
    return info


def get_recent_activity() -> list:
    """جلب آخر الأنشطة من ذاكرة WeaverCode"""
    activities = []
    try:
        db_path = _db_path()
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            rows = conn.execute(
                "SELECT prompt, created_at FROM conversations "
                "ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            conn.close()
            now = time.time()
            for prompt, ts in rows:
                ts = ts or now
                diff = max(0, now - ts)
                if diff < 3600:
                    age = f"{int(diff / 60)}m"
                elif diff < 86400:
                    age = f"{int(diff / 3600)}h"
                else:
                    age = f"{int(diff / 86400)}d"
                prompt = (prompt or "").strip()
                activities.append((age, prompt[:35] + ("…" if len(prompt) > 35 else "")))
    except Exception:
        pass
    if not activities:
        activities = [("—", "لا نشاط سابق")]
    return activities


def get_stats() -> int:
    """عدد المحادثات المحفوظة"""
    try:
        db_path = _db_path()
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            convs = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            conn.close()
            return convs
    except Exception:
        pass
    return 0


def get_version() -> str:
    """رقم الإصدار (يُلحق hash من git إن توفّر)"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(_project_root()),
        )
        h = result.stdout.strip()
        if h:
            return f"{WEAVER_VERSION}·{h}"
    except Exception:
        pass
    return WEAVER_VERSION


# ── العنكبوت ASCII ────────────────────────────────────────────────────────
# ملاحظة: نستخدم سلاسل خام (raw) لتفادي مشاكل تسلسلات الهروب مثل \/ و \\
def _spider_art() -> list:
    return [
        rf"{OR}    ██╗    ██╗{RST}",
        rf"{OR}   ████╗  ████╗{RST}",
        rf"{OR}  ██╔╝  ██  ╚██╗{RST}",
        rf"{OR}  ██║  {WHT}(oo){OR}  ██║{RST}",
        rf"{OR}  ╚██╗  \/  ╔██╝{RST}",
        rf"{OR}  / ████████ \ {RST}",
        rf"{OR} /  /      \  \ {RST}",
        rf"{OR}/__/        \__\{RST}",
    ]


# ── الواجهة الرئيسية ───────────────────────────────────────────────────────

def draw_welcome(model: str = "", provider: str = ""):
    """شاشة الاستقبال الكاملة بعمودين"""
    cls()
    W = max(60, term_width())
    env = get_env_info()
    if model:
        env["model"] = model
    if provider:
        env["provider"] = provider
    activities = get_recent_activity()
    stats = get_stats()
    ver = get_version()

    # ── الإطار العلوي + العنوان ────────────────────────────────────────────
    print(f"{OR}{'·' * W}{RST}")
    print(f"  {OR}{BLD}🕸️  W E A V E R C O D E{RST}  {GRY}{ver}{RST}")
    print(f"{OR}{'·' * W}{RST}")
    print()

    # ── تجهيز العمودين ─────────────────────────────────────────────────────
    left_w = W // 2 - 2

    left_lines = []
    user = os.environ.get("USER") or os.environ.get("USERNAME") or "Bashar"
    left_lines.append(f"  {OR2}{BLD}أهلاً {user}!{RST}")
    left_lines.append("")
    for line in _spider_art():
        left_lines.append(f"  {line}")
    left_lines.append("")
    left_lines.append(f"  {GRY}النموذج:{RST}  {OR}{env['model']}{RST}")
    left_lines.append(f"  {GRY}المزود: {RST}  {GR2}{env['provider']}{RST}")
    left_lines.append(f"  {GRY}المفتاح:{RST}  " +
                      (f"{GRN}✓ {env.get('key_preview', '···')}{RST}" if env['key_set']
                       else f"{RED}✗ غير محدد{RST}"))
    left_lines.append(f"  {GRY}المسار: {RST}  {DIM}{Path.cwd()}{RST}")
    left_lines.append(f"  {GRY}المحادثات:{RST} {OR}{stats}{RST}")

    right_lines = []
    right_lines.append(f"{OR2}{BLD}آخر النشاطات{RST}")
    right_lines.append(f"{OR}{'─' * 28}{RST}")
    for age, act in activities[:5]:
        right_lines.append(f"  {GRY}{age:<4}{RST}  {GR2}{act}{RST}")
    right_lines.append("")
    right_lines.append(f"{OR2}{BLD}ما الجديد{RST}")
    right_lines.append(f"{OR}{'─' * 28}{RST}")
    for n in [
        "🕸️  44 أداة مدمجة",
        "🔧  دعم كل المزودين",
        "🧠  ذاكرة SQLite دائمة",
        "⚡  وضع Anthropic + OpenAI",
        "🔑  /weaver-key لتغيير المفتاح",
    ]:
        right_lines.append(f"  {GR2}{n}{RST}")
    right_lines.append("")
    right_lines.append(f"{GRY}/weaver-help للمزيد{RST}")

    # ── طباعة العمودين جنباً إلى جنب ───────────────────────────────────────
    max_lines = max(len(left_lines), len(right_lines))
    left_lines += [""] * (max_lines - len(left_lines))
    right_lines += [""] * (max_lines - len(right_lines))

    sep = f"{OR}│{RST}"
    for l, r in zip(left_lines, right_lines):
        pad = max(0, left_w - _visible_len(l))
        print(f" {l}{' ' * pad} {sep} {r}")

    print()
    print(f"{OR}{'·' * W}{RST}")

    # ── سطر النجوم المتناثرة ───────────────────────────────────────────────
    star_positions = {3, 11, 19, 31, 45, 58, 67, W - 5}
    stars_line = "".join(
        f"{GRY}*{RST}" if i in star_positions else f"{DIM}·{RST}"
        for i in range(W)
    )
    print(stars_line)

    # ── الشريط السفلي (الاختصارات) ─────────────────────────────────────────
    print()
    status_bar = (
        f"  {OR}[k]{RST}{GRY} مفتاح  {RST}"
        f"{OR}[m]{RST}{GRY} الوضع  {RST}"
        f"{OR}[h]{RST}{GRY} مساعدة {RST}"
        f"{OR}[q]{RST}{GRY} خروج   {RST}"
    )
    print(status_bar)
    print(f"{OR}{'·' * W}{RST}")
    print()


def draw_split_header(model: str, provider: str):
    """رأس الشاشة المنقسمة أثناء العمل"""
    W = max(60, term_width())
    half = W // 2
    left = f" {OR}🕸️  WeaverCode{RST}"
    right = f" {GRY}النموذج: {OR}{model}{RST} {GRY}│ {provider}{RST}"

    pad = max(0, half - _visible_len(left) - 1)
    print(f"{OR}{'·' * W}{RST}")
    print(f"{left}{' ' * pad}{OR}│{RST}{right}")
    print(f"{OR}{'·' * W}{RST}")


def draw_thinking(msg: str = "يعالج..."):
    """مؤشر التفكير (إطار واحد — للاستدعاء المتكرر)"""
    frames = ["🕸 ", "🕷 ", "🕸 ", "  "]
    f = frames[int(time.time() * 3) % len(frames)]
    sys.stdout.write(f"\r  {OR}{f}{RST} {GRY}{msg}{RST}")
    sys.stdout.flush()


def draw_tool_call(name: str, arg: str = "", in_progress: bool = True):
    """
    عرض حالة الأداة أثناء التنفيذ (بصيغة Action Blocks).
    يُستبدَل بـ draw_action_block بعد انتهاء الجولة.

    مثال:  ‹ Creating build.js ...
    """
    _PROGRESSIVE = {
        "Write": "Creating", "Edit": "Editing", "MultiEdit": "Editing",
        "Read": "Reading", "Bash": "Running", "PythonRun": "Running",
        "Glob": "Searching", "Grep": "Searching", "WebFetch": "Fetching",
        "WebSearch": "Searching", "GitClone": "Cloning",
        "GitCommit": "Committing", "GitPush": "Pushing",
        "PipInstall": "Installing", "Agent": "Running sub-agent",
        "MemorySave": "Saving", "TaskCreate": "Creating task",
        "DirectoryList": "Listing", "LSP": "Checking",
    }
    verb = _PROGRESSIVE.get(name, "Running")
    arg = str(arg or "")
    fname = Path(arg).name if arg and "/" in arg else arg
    label = f"{verb} {fname[:50]}" if fname else verb
    dots = " ..." if in_progress else ""
    if _is_tty():
        sys.stdout.write("\r\033[K")
    print(f"  {GRY}‹{RST} {GRY}{label}{dots}{RST}")


def clear_tool_line() -> None:
    """مسح سطر حالة الأداة الجارية من الطرفية (في TTY فقط)."""
    if _is_tty():
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()


def draw_action_block(block, clear_previous: bool = True) -> None:
    """
    عرض Action Block المكتمل بعد انتهاء جولة الأدوات.
        ‹ 1- +11  Edited a file, read a file
    """
    from core.action_blocks import ActionBlock  # تأجيل الاستيراد لتفادي الدوران
    if not isinstance(block, ActionBlock):
        return
    if clear_previous and _is_tty():
        sys.stdout.write("\r\033[K")

    if block.in_progress:
        line = block.in_progress_line()
        sys.stdout.write(f"  {OR}‹{RST} {GRY}{line}{RST}")
        sys.stdout.flush()
        return

    if not block.ops:
        return

    removed = block.lines_removed
    added = block.lines_added
    desc = block._build_description()
    parts = [f"  {OR}‹{RST} "]
    if block.has_diff:
        parts.append(f"{RED}{removed}-{RST} ")
        parts.append(f"{GRN}+{added}{RST}  ")
    else:
        parts.append(f"{GRY}     {RST}")
    parts.append(f"{GRY}{desc}{RST}")
    print("".join(parts))


def draw_action_block_inline(block) -> str:
    """إرجاع Action Block كنص عادي (لـ SSE أو logging) بلا ألوان."""
    from core.action_blocks import ActionBlock
    if not isinstance(block, ActionBlock) or not block.ops:
        return ""
    removed = block.lines_removed
    added = block.lines_added
    desc = block._build_description()
    if block.has_diff:
        return f"  ‹ {removed}- +{added}  {desc}"
    return f"  ‹ {desc}"


def draw_response(text: str):
    """عرض رد WeaverCode"""
    print(f"\n{OR}🕸️{RST}  {text}\n")


def draw_error(text: str):
    print(f"\n{RED}✗ {text}{RST}\n")


def draw_success(text: str):
    print(f"{GRN}✓ {text}{RST}")


def draw_info(text: str):
    print(f"{GRY}ℹ️  {text}{RST}")


def draw_stats(turns: int, tools: list, blocks: list = None):
    """إحصاءات بعد الرد مع ملخص Action Blocks (blocks اختياري)."""
    if not tools and not blocks:
        return
    if blocks:
        total_r = sum(getattr(b, "lines_removed", 0) for b in blocks)
        total_a = sum(getattr(b, "lines_added", 0) for b in blocks)
        if total_r or total_a:
            print(f"\n{GRY}📊 {turns} دورة │ {RED}{total_r}-{RST}{GRY} "
                  f"{GRN}+{total_a}{RST}{GRY} │ "
                  f"{', '.join(dict.fromkeys(tools))}{RST}")
            return
    if tools:
        print(f"\n{GRY}📊 {turns} دورة │ {', '.join(dict.fromkeys(tools))}{RST}")


def draw_prompt() -> str:
    """سطر الإدخال في الوضع التفاعلي"""
    return input(f"\n{OR}❯{RST} أنت: ").strip()


def draw_separator():
    print(f"{OR}{'·' * max(60, term_width())}{RST}")


def draw_permission_request(name: str, preview: str = ""):
    """عرض صندوق طلب صلاحية قبل تنفيذ أداة خطرة"""
    w = max(44, min(term_width(), 64))
    p = f"  {DIM}{preview[:80]}{RST}" if preview else ""
    print(f"\n{OR}{'─' * w}{RST}")
    print(f"  {OR}{BLD}🔐 طلب صلاحية{RST}")
    print(f"  {GRY}الأداة:{RST} {OR}{name}{RST}")
    if p:
        print(p)
    print(f"  {GRN}[y]{RST} سماح مرة   "
          f"{OR}[a]{RST} سماح دائم   "
          f"{RED}[n]{RST} رفض")
    print(f"{OR}{'─' * w}{RST}")


# ── مؤشر تفكير غير متزامن (Spinner) ───────────────────────────────────────

class Spinner:
    """
    مؤشر تفكير متحرك يعمل أثناء انتظار رد المزود.
    يُفعَّل فقط في الطرفية التفاعلية.
    """

    FRAMES = ["🕸 ", "🕷 "]

    def __init__(self, msg: str = "يعالج..."):
        self.msg = msg
        self.enabled = _is_tty()
        self._task = None
        self._stop = None

    async def _run(self):
        import asyncio
        i = 0
        while not self._stop.is_set():
            f = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r  {OR}{f}{RST} {GRY}{self.msg}{RST}")
            sys.stdout.flush()
            i += 1
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=0.35)
            except asyncio.TimeoutError:
                pass
        clear_line()

    def start(self):
        if not self.enabled:
            return
        import asyncio
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        if not self.enabled or not self._task:
            return
        self._stop.set()
        try:
            await self._task
        except Exception:
            pass
        clear_line()

    def clear(self):
        """مسح سطر المؤشر مؤقتاً (قبل طباعة سطر أداة مثلاً)"""
        if self.enabled:
            clear_line()


# ── دوال الأيقونات (assets) ────────────────────────────────────────────────

def get_icon_path(name: str = "icon_internal_256.png") -> Path:
    """مسار الأيقونة في مجلد assets بجذر المشروع"""
    return _project_root() / "assets" / name


def icon_exists() -> bool:
    return get_icon_path().exists()


def try_show_terminal_image(path: Path, width: int = 64) -> bool:
    """محاولة عرض الأيقونة في الطرفية (بروتوكول Kitty)"""
    if not path.exists():
        return False
    if os.environ.get("TERM") == "xterm-kitty":
        try:
            import base64
            data = path.read_bytes()
            b64 = base64.standard_b64encode(data).decode()
            chunk_size = 4096
            chunks = [b64[i:i + chunk_size] for i in range(0, len(b64), chunk_size)]
            for i, chunk in enumerate(chunks):
                m = 1 if i < len(chunks) - 1 else 0
                if i == 0:
                    sys.stdout.write(f"\033_Ga=T,f=100,m={m},c={width},r=8;{chunk}\033\\")
                else:
                    sys.stdout.write(f"\033_Gm={m};{chunk}\033\\")
            sys.stdout.write("\n")
            sys.stdout.flush()
            return True
        except Exception:
            pass
    return False


def show_startup_icon():
    """عرض أيقونة البدء إن أمكن (وإلا يكفي البانر النصي)"""
    try_show_terminal_image(get_icon_path("icon_internal_64.png"), width=8)


# ── أسماء متوافقة رجعياً (Wrappers) ───────────────────────────────────────

def show_banner(model: str = "", provider_url: str = ""):
    """توافق رجعي: يعرض شاشة الاستقبال الكاملة"""
    provider = provider_url.split("//")[-1].split("/")[0] if provider_url else ""
    draw_welcome(model=model, provider=provider)


def show_mini_banner():
    draw_split_header(os.environ.get("WEAVER_MODEL", ""),
                      (os.environ.get("WEAVER_BASE_URL", "").split("//")[-1].split("/")[0]))


def format_tool_call(name: str, arg: str = "") -> str:
    arg_str = f"({str(arg)[:50]})" if arg else ""
    return f"  {OR}🔧 {name}{RST}{GRY}{arg_str}{RST}"


def format_response(text: str) -> str:
    return f"\n{OR}🕸️{RST}  {text}"


def format_error(text: str) -> str:
    return f"\n{RED}✗ {text}{RST}"


def format_success(text: str) -> str:
    return f"{GRN}✓ {text}{RST}"


def format_info(text: str) -> str:
    return f"{GRY}ℹ️  {text}{RST}"


def print_stats(turns: int, tools: list, cost_info: str = ""):
    draw_stats(turns, tools)
    if cost_info:
        print(f"{GRY}💰 {cost_info}{RST}")


if __name__ == "__main__":
    # اختبار الواجهة
    draw_welcome("claude-fable-5", "capi.aerolink.lat")
    draw_split_header("claude-fable-5", "capi.aerolink.lat")
    print()
    draw_tool_call("Read", "weaver.py")
    draw_tool_call("Bash", "python3 --version")
    draw_response("مرحباً! أنا WeaverCode جاهز للعمل 🕸️")
    draw_stats(2, ["Read", "Bash"])
    draw_separator()
