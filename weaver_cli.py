#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weaver-cli.py — WeaverCode cross-platform management CLI 🕸️
============================================================
One command to install, run, restore, update, configure, diagnose and fix
WeaverCode on ANY system: Android (Termux), Windows, macOS and Linux.

Usage:
    python weaver-cli.py <command> [args]

Commands:
    install              Install dependencies and set everything up
    start | up | web     Start the dashboard + daemon in the background, print the URL
    stop | down          Stop all WeaverCode servers
    restart | restore    Restart (use this after closing the device or terminal)
    status               Show what's running + the web URL + provider/model
    url                  Print the web login URL(s)
    open                 Print the URL and try to open it in a browser
    update [branch]      Pull the latest code, update deps, restart, verify
    provider <name>      Switch AI provider (openrouter/groq/deepseek/…)
    key <API_KEY>        Set the API key (auto-detects the provider)
    model <name>         Set the model
    doctor | diagnose    Run health checks and report problems
    fix                  Auto-fix common problems (dirs, .env, stuck port, deps)
    backup [dest]        Back up memory + sessions to a portable .tar.gz (--keep N)
    backups              List existing backups
    restore-backup <f>   Restore memory + sessions from a backup (--overwrite)
    symbols <sub>        Code symbol index: build | find <name> | outline <file>
    logs [N]             Show the last N lines of the server log (default 40)
    banner | hello       Show the WeaverCode hero banner
    version              Print the WeaverCode version
    help                 Show this help

The CLI is stdlib-only, so it runs wherever Python 3.8+ runs.
"""
from __future__ import annotations

import os
import sys
import time
import signal
import shutil
import socket
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── colors (disabled when not a TTY or on legacy Windows) ────────────────────
def _supports_color() -> bool:
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        return bool(os.environ.get("WT_SESSION") or os.environ.get("ANSICON")
                    or "TERM" in os.environ)
    return True

_C = _supports_color()
OR = "\033[38;2;198;113;33m" if _C else ""
GN = "\033[32m" if _C else ""
RD = "\033[31m" if _C else ""
GY = "\033[90m" if _C else ""
BD = "\033[1m" if _C else ""
RS = "\033[0m" if _C else ""

WEB = ROOT / "web" / "server.py"
HOME_WEAVER = Path.home() / ".weaver"
LOG_DIR = HOME_WEAVER / "logs"
PID_FILE = HOME_WEAVER / "web.pid"
LOG_FILE = LOG_DIR / "web.log"


# ── platform helpers ─────────────────────────────────────────────────────────
def is_termux() -> bool:
    return ("com.termux" in os.environ.get("PREFIX", "")
            or Path("/data/data/com.termux/files/usr").exists())


def is_windows() -> bool:
    return os.name == "nt"


def platform_name() -> str:
    if is_termux():
        return "Android (Termux)"
    if is_windows():
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return "Linux"


def say(msg: str) -> None:
    print(f"{OR}🕸️{RS}  {msg}")


def ok(msg: str) -> None:
    print(f"  {GN}✓{RS} {msg}")


def bad(msg: str) -> None:
    print(f"  {RD}✗{RS} {msg}")


def info(msg: str) -> None:
    print(f"  {GY}•{RS} {msg}")


def web_host() -> str:
    return os.environ.get("WEAVER_WEB_HOST", "127.0.0.1")


def web_port() -> int:
    try:
        return int(os.environ.get("WEAVER_WEB_PORT", "8080"))
    except ValueError:
        return 8080


def _lan_ip() -> str:
    """Best-effort LAN IP (for opening the dashboard from another device)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def urls() -> list:
    port = web_port()
    out = [f"http://127.0.0.1:{port}"]
    if web_host() == "0.0.0.0":
        out.append(f"http://{_lan_ip()}:{port}   (from other devices on your network)")
    return out


# ── process management (cross-platform background start/stop) ────────────────
def _pip_cmd() -> list:
    return [sys.executable, "-m", "pip"]


def _pip_install(pkgs: list) -> bool:
    """Install packages, tolerating Termux/externally-managed environments."""
    base = _pip_cmd() + ["install", "-q"] + pkgs
    for extra in ([], ["--break-system-packages"], ["--user"]):
        try:
            r = subprocess.run(base + extra, cwd=str(ROOT))
            if r.returncode == 0:
                return True
        except Exception:
            continue
    return False


def _read_pid() -> int:
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return 0


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        if is_windows():
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                                 capture_output=True, text=True)
            return str(pid) in out.stdout
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def is_running() -> int:
    """Return the running server PID (0 if not running)."""
    pid = _read_pid()
    if pid and _pid_alive(pid):
        return pid
    # fall back to a port probe (server may have been started another way)
    if _port_in_use(web_port()):
        return -1   # running but PID unknown
    return 0


def _port_in_use(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.4)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def start(_args=None) -> int:
    if not WEB.exists():
        bad(f"Cannot find {WEB} — run this from the WeaverCode folder.")
        return 1
    running = is_running()
    if running:
        say("WeaverCode is already running.")
        _print_urls()
        return 0
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # free a stuck port from a previous crashed run
    stop(silent=True)
    logf = open(LOG_FILE, "ab")
    kwargs = {"cwd": str(ROOT), "stdout": logf, "stderr": logf,
              "stdin": subprocess.DEVNULL}
    if is_windows():
        DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | NEW_PROCESS_GROUP
        kwargs["creationflags"] = DETACHED
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen([sys.executable, str(WEB)], **kwargs)
    PID_FILE.write_text(str(proc.pid))
    # wait until the port answers (up to ~8s)
    for _ in range(40):
        time.sleep(0.2)
        if _port_in_use(web_port()):
            break
    if is_running():
        say(f"WeaverCode Dashboard is running (PID {proc.pid}).")
        _print_urls()
        info(f"Log: {LOG_FILE}   ·   Stop: python weaver-cli.py stop")
        return 0
    bad("The server did not start — check the log:")
    _tail(LOG_FILE, 8)
    return 1


def stop(_args=None, silent: bool = False) -> int:
    killed = False
    pid = _read_pid()
    if pid and _pid_alive(pid):
        try:
            if is_windows():
                subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                               capture_output=True)
            else:
                os.kill(pid, signal.SIGTERM)
            killed = True
        except Exception:
            pass
    # best-effort sweep of any stray server processes
    try:
        if is_windows():
            subprocess.run(
                ["wmic", "process", "where",
                 "commandline like '%web/server.py%' or commandline like '%web\\\\server.py%'",
                 "delete"], capture_output=True)
        else:
            subprocess.run(["pkill", "-f", "web/server.py"], capture_output=True)
    except Exception:
        pass
    try:
        PID_FILE.unlink()
    except Exception:
        pass
    if not silent:
        if killed:
            say("WeaverCode stopped (all servers).")
        else:
            say("No running WeaverCode server was found.")
    return 0


def restart(_args=None) -> int:
    stop(silent=True)
    time.sleep(1)
    return start()


def _print_urls() -> None:
    for u in urls():
        print(f"    {OR}{u}{RS}")


def status(_args=None) -> int:
    say(f"WeaverCode status  ·  {platform_name()}")
    pid = is_running()
    if pid > 0:
        ok(f"Running (PID {pid})")
    elif pid == -1:
        ok("Running (started outside this CLI)")
    else:
        bad("Not running   ·   start it with: python weaver-cli.py start")
    if pid:
        print(f"  {GY}Web:{RS}")
        _print_urls()
    env = _read_env()
    print(f"  {GY}Model:{RS}    {env.get('WEAVER_MODEL', '(not set)')}")
    print(f"  {GY}Provider:{RS} {env.get('WEAVER_BASE_URL', '(not set)')}")
    print(f"  {GY}API key:{RS}  " + ("set ✓" if env.get('WEAVER_API_KEY') else "MISSING ✗"))
    # أمان اللوحة: تنبيه إن كانت مفتوحة للشبكة بلا توكن
    _host = web_host()
    _tok = (env.get("WEAVER_WEB_TOKEN") or os.environ.get("WEAVER_WEB_TOKEN") or "").strip()
    if _host == "0.0.0.0" and not _tok:
        bad("Dashboard is open to your network WITHOUT a token — set WEAVER_WEB_TOKEN")
    elif _host == "0.0.0.0":
        ok("Dashboard open to network, protected by token 🔑")
    else:
        ok("Dashboard is local-only (this device) 🔒")
    return 0


def url_cmd(_args=None) -> int:
    for u in urls():
        print(u)
    return 0


def open_cmd(_args=None) -> int:
    u = urls()[0]
    print(u)
    try:
        if is_termux():
            subprocess.run(["termux-open-url", u], check=False)
        elif is_windows():
            os.startfile(u)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", u], check=False)
        else:
            subprocess.run(["xdg-open", u], check=False)
    except Exception:
        pass
    return 0


# ── config (.env) helpers ────────────────────────────────────────────────────
ENV_FILE = ROOT / "config" / ".env"


def _read_env() -> dict:
    out = {}
    for src in (ENV_FILE,):
        if src.exists():
            for raw in src.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.startswith("export "):
                    line = line[7:].strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                out[k.strip()] = v
    # environment overrides file
    for k in ("WEAVER_MODEL", "WEAVER_BASE_URL", "WEAVER_API_KEY"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def _save_env(updates: dict) -> None:
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    for key, value in updates.items():
        value = str(value)
        done = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                lines[i] = f"{key}={value}"
                done = True
                break
        if not done:
            lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def provider_cmd(args) -> int:
    if not args:
        try:
            from core import providers
            names = ", ".join(providers.provider_names())
        except Exception:
            names = "openrouter, groq, deepseek, anthropic, openai, together, ollama"
        bad("Usage: python weaver-cli.py provider <name>")
        info(f"Available: {names}")
        return 1
    name = args[0].strip().lower()
    try:
        from core import providers
        entry = providers.get_provider(name)
    except Exception:
        entry = None
    if not entry:
        bad(f"Unknown provider: {name}")
        return 1
    updates = {"WEAVER_BASE_URL": entry["base_url"]}
    if entry.get("model"):
        updates["WEAVER_MODEL"] = entry["model"]
    _save_env(updates)
    ok(f"Provider set to {name}  ·  {entry['base_url']}")
    if entry.get("model"):
        info(f"Model: {entry['model']}  (change with: python weaver-cli.py model <name>)")
    info("Restart to apply: python weaver-cli.py restart")
    return 0


def key_cmd(args) -> int:
    if not args:
        bad("Usage: python weaver-cli.py key <API_KEY>")
        return 1
    key = args[0].strip()
    updates = {"WEAVER_API_KEY": key}
    # auto-detect the provider from the key prefix
    try:
        from core import providers
        e = providers.detect_by_prefix(key)
        if e:
            updates["WEAVER_BASE_URL"] = e["base_url"]
            if e.get("model"):
                updates.setdefault("WEAVER_MODEL", e["model"])
    except Exception:
        e = None
    _save_env(updates)
    ok("API key saved.")
    if e:
        info(f"Detected provider: {e['name']}  ·  {e['base_url']}")
    info("Restart to apply: python weaver-cli.py restart")
    return 0


def model_cmd(args) -> int:
    if not args:
        bad("Usage: python weaver-cli.py model <name>")
        return 1
    _save_env({"WEAVER_MODEL": args[0].strip()})
    ok(f"Model set to {args[0].strip()}")
    info("Restart to apply: python weaver-cli.py restart")
    return 0


# ── install ──────────────────────────────────────────────────────────────────
_DEPS = ["httpx", "python-dotenv", "rich", "nbformat", "watchdog", "pyflakes"]


def _requirements() -> list:
    """Package list from config/requirements.txt, or the safe default set.

    Strips inline comments (``pkg>=1.0  # note``) which pip would reject.
    """
    req = ROOT / "config" / "requirements.txt"
    if req.exists():
        pkgs = []
        for raw in req.read_text(encoding="utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()   # drop inline + full-line comments
            if line:
                pkgs.append(line)
        if pkgs:
            return pkgs
    return _DEPS


def install(_args=None) -> int:
    say(f"Installing WeaverCode  ·  {platform_name()}")
    # 1) system dirs
    for d in ("logs", "cache", "sessions", "backup"):
        (HOME_WEAVER / d).mkdir(parents=True, exist_ok=True)
    ok("Created ~/.weaver directories")
    # 2) python deps (from requirements.txt when available, else a safe default)
    info("Installing Python dependencies…")
    if _pip_install(_requirements()):
        ok("Dependencies installed")
    else:
        bad("Some dependencies failed to install — run 'doctor' to see which")
    # 3) .env from example
    if not ENV_FILE.exists():
        ex = ROOT / "config" / ".env.example"
        if ex.exists():
            shutil.copy(ex, ENV_FILE)
            ok("Created config/.env (add your API key)")
    else:
        ok("config/.env already exists")
    # 4) global launcher on POSIX (so `weaver` works anywhere)
    if not is_windows():
        try:
            bindir = Path.home() / ".local" / "bin"
            bindir.mkdir(parents=True, exist_ok=True)
            launcher = bindir / "weaver"
            launcher.write_text(
                "#!/usr/bin/env bash\n"
                f'exec "{sys.executable}" "{ROOT / "weaver-cli.py"}" "$@"\n')
            launcher.chmod(0o755)
            ok(f"Installed 'weaver' command → {launcher}")
            info("If 'weaver' is not found, add to PATH: "
                 'export PATH="$HOME/.local/bin:$PATH"')
        except Exception:
            pass
    print()
    say("Installed! Next steps:")
    info("1) Add your API key:   python weaver-cli.py key <API_KEY>")
    info("2) Start the dashboard: python weaver-cli.py start")
    info("3) Open the printed URL in your browser.")
    return 0


# ── update ───────────────────────────────────────────────────────────────────
def update(args) -> int:
    say("Updating WeaverCode…")
    branch = args[0] if args else _git("rev-parse", "--abbrev-ref", "HEAD").strip() or "main"
    info(f"Branch: {branch}")
    # protect local changes (e.g. config/.env)
    dirty = bool(_git("status", "--porcelain").strip())
    stashed = False
    if dirty:
        info("Stashing your local changes…")
        if _git("stash", "push", "-u", "-m", f"weaver-update-{int(time.time())}"):
            stashed = True
    # pull with retries
    pulled = False
    for i in range(1, 5):
        _git("fetch", "origin", branch)
        if _git("pull", "--ff-only", "origin", branch, ok_fail=True) is not None:
            pulled = True
            break
        info(f"Pull failed — retry {i}…")
        time.sleep(2 ** i)
    if pulled:
        ok("Pulled the latest code")
    else:
        bad("Could not pull (network?) — try again later")
    if stashed:
        _git("stash", "pop", ok_fail=True)
        info("Restored your local changes")
    # deps + restart
    _pip_install(_requirements())
    ok("Dependencies updated")
    if os.environ.get("WEAVER_NO_RESTART") != "1":
        restart()
    return 0


def _git(*args, ok_fail: bool = False):
    try:
        r = subprocess.run(["git", *args], cwd=str(ROOT),
                           capture_output=True, text=True)
        if r.returncode != 0 and not ok_fail:
            return ""
        if r.returncode != 0:
            return None
        return r.stdout
    except Exception:
        return None if ok_fail else ""


# ── doctor / diagnose ────────────────────────────────────────────────────────
def doctor(_args=None) -> int:
    say(f"WeaverCode doctor  ·  {platform_name()}")
    problems = 0

    # python version
    if sys.version_info >= (3, 8):
        ok(f"Python {sys.version.split()[0]}")
    else:
        bad(f"Python {sys.version.split()[0]} is too old (need 3.8+)"); problems += 1

    # git
    if shutil.which("git"):
        ok("git found")
    else:
        bad("git not found (needed for update)"); problems += 1

    # curl — REQUIRED: the provider shells out to curl (not httpx) for every call
    if shutil.which("curl"):
        ok("curl found (used by the provider)")
    else:
        bad("curl not found — the provider needs it: "
            "install it (apt install curl / pkg install curl on Termux)")
        problems += 1

    # httpx — OPTIONAL: only speeds up WebFetch; it falls back to curl without it
    try:
        __import__("httpx")
        ok("optional 'httpx' available (faster WebFetch)")
    except Exception:
        info("optional 'httpx' not installed — WebFetch falls back to curl (fine)")

    # config
    if ENV_FILE.exists():
        ok("config/.env present")
    else:
        bad("config/.env missing — run: python weaver-cli.py fix"); problems += 1
    env = _read_env()
    if env.get("WEAVER_API_KEY"):
        ok("API key set")
    else:
        bad("API key missing — set it: python weaver-cli.py key <API_KEY>"); problems += 1
    if env.get("WEAVER_BASE_URL"):
        ok(f"Provider URL: {env['WEAVER_BASE_URL']}")
    else:
        bad("Provider URL missing — set: python weaver-cli.py provider <name>"); problems += 1

    # provider reachability (optional, best-effort)
    if env.get("WEAVER_API_KEY") and env.get("WEAVER_BASE_URL"):
        if _provider_reachable(env):
            ok("Provider endpoint reachable")
        else:
            bad("Provider endpoint not reachable (check key/URL/network)"); problems += 1

    # server + port
    if is_running():
        ok("Server running")
    else:
        info("Server not running (start: python weaver-cli.py start)")
    if _port_in_use(web_port()) and not is_running():
        bad(f"Port {web_port()} is busy but not ours — run: python weaver-cli.py fix"); problems += 1

    print()
    if problems == 0:
        say(f"{GN}All checks passed. WeaverCode is healthy.{RS}")
    else:
        say(f"{RD}{problems} problem(s) found.{RS} Try: python weaver-cli.py fix")
    return 0 if problems == 0 else 1


def _provider_reachable(env: dict) -> bool:
    base = env["WEAVER_BASE_URL"].rstrip("/")
    root = base[:-3].rstrip("/") if base.lower().endswith("/v1") else base
    key = env["WEAVER_API_KEY"]
    import urllib.request
    for u in (root + "/v1/models", root + "/models", base + "/models"):
        for hdr in ({"Authorization": f"Bearer {key}"}, {"x-api-key": key}):
            try:
                req = urllib.request.Request(u, headers={**hdr, "User-Agent": "WeaverCode"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    if r.status < 500:
                        return True
            except urllib.error.HTTPError as e:  # noqa
                if e.code < 500:
                    return True
            except Exception:
                continue
    return False


# ── fix ──────────────────────────────────────────────────────────────────────
def fix(_args=None) -> int:
    say("Fixing common problems…")
    # dirs
    for d in ("logs", "cache", "sessions", "backup"):
        (HOME_WEAVER / d).mkdir(parents=True, exist_ok=True)
    ok("Ensured ~/.weaver directories")
    # .env
    if not ENV_FILE.exists():
        ex = ROOT / "config" / ".env.example"
        if ex.exists():
            shutil.copy(ex, ENV_FILE); ok("Restored config/.env from example")
    # deps
    info("Reinstalling dependencies…")
    _pip_install(_requirements()); ok("Dependencies reinstalled")
    # stale flags / pid
    for f in (HOME_WEAVER / "cancel.flag", PID_FILE):
        try:
            f.unlink(); info(f"Removed stale {f.name}")
        except Exception:
            pass
    # stuck port (ours) → stop
    if _port_in_use(web_port()):
        info(f"Freeing port {web_port()}…")
        stop(silent=True)
    say("Done. Now run: python weaver-cli.py start")
    return 0


# ── backup / restore (memory + sessions) ─────────────────────────────────────
def _human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def backup_cmd(args) -> int:
    """Create a portable backup of the memory DB + saved sessions.

    Usage: backup [dest] [--keep N]   (--keep prunes old backups in the
    default folder, keeping only the newest N)."""
    try:
        from core import backup as _bk
    except Exception as e:
        bad(f"Could not load backup module: {e}")
        return 1
    # parse args: optional dest + optional --keep N
    dest = None
    keep = None
    it = iter(args or [])
    for a in it:
        if a in ("--keep", "-k"):
            try:
                keep = int(next(it))
            except (StopIteration, ValueError):
                bad("--keep needs a number, e.g. --keep 5")
                return 1
        elif dest is None:
            dest = a
    say("Backing up WeaverCode memory + sessions…")
    try:
        out = _bk.create_backup(dest)
    except Exception as e:
        bad(f"Backup failed: {e}")
        return 1
    try:
        counts = _bk.export_json()
        n_conv = len(counts.get("conversations", []))
        n_sess = len(counts.get("sessions", []))
        n_fact = len(counts.get("facts", []))
        info(f"{n_conv} conversations · {n_sess} sessions · {n_fact} facts")
    except Exception:
        pass
    ok(f"Backup written → {out}")
    info(f"Size: {_human_size(out.stat().st_size)}")
    if keep is not None:
        removed = _bk.prune_backups(keep)
        if removed:
            info(f"Pruned {len(removed)} old backup(s) · kept newest {keep}")
    info("Restore later with: python weaver-cli.py restore-backup <file>")
    return 0


def symbols_cmd(args) -> int:
    """Query the code symbol index: build | find <name> | outline <file>."""
    try:
        from core.index import symbols as _sym
    except Exception as e:
        bad(f"Could not load symbol index: {e}")
        return 1
    sub = (args[0].lower() if args else "build")
    rest = args[1:]
    root = str(ROOT)
    if sub == "build":
        path = rest[0] if rest else root
        idx = _sym.build_index(path, cache=True, incremental=True)
        extra = (f"  ({idx['reused_files']} unchanged)"
                 if idx.get("reused_files") else "")
        ok(f"Indexed {idx['count']} symbols from {idx['files']} files{extra}")
        return 0
    # find / outline need an index — load cache or build it
    path = rest[1] if len(rest) > 1 else root
    idx = _sym.load_index(path) or _sym.build_index(path, cache=True)
    if sub == "find":
        if not rest:
            bad("Usage: symbols find <name> [path]")
            return 1
        rows = _sym.find(idx, rest[0])
        if not rows:
            say(f"No symbol named '{rest[0]}'.")
            return 0
        say(f"Results for '{rest[0]}' ({len(rows)}):")
        for s in rows:
            print(f"  {OR}{s['file']}:{s['line']}{RS}  [{s['kind']}] "
                  f"{s.get('signature', s['name'])}")
        return 0
    if sub == "outline":
        if not rest:
            bad("Usage: symbols outline <file> [path]")
            return 1
        rows = _sym.outline(idx, rest[0])
        if not rows:
            say(f"No indexed symbols for: {rest[0]}")
            return 0
        say(f"{rest[0]} — {len(rows)} symbols:")
        for s in rows:
            print(f"  {s['line']:>4}  {s['kind']:<9} {s.get('signature', s['name'])}")
        return 0
    bad(f"Unknown symbols action: {sub}  (build | find | outline)")
    return 1


def backups_cmd(_args=None) -> int:
    """List backups in ~/.weaver/backup."""
    try:
        from core import backup as _bk
    except Exception as e:
        bad(f"Could not load backup module: {e}")
        return 1
    items = _bk.list_backups()
    if not items:
        say("No backups yet. Create one with: python weaver-cli.py backup")
        return 0
    say(f"Backups ({len(items)}):")
    for it in items:
        man = it.get("manifest", {})
        counts = man.get("counts", {})
        when = man.get("created_at_human", "")
        summary = ""
        if counts:
            summary = (f"  ·  {counts.get('conversations', 0)} conv, "
                       f"{counts.get('sessions', 0)} sess")
        print(f"  {OR}{it['name']}{RS}  ({_human_size(it['size'])}){summary}"
              + (f"  ·  {when}" if when else ""))
    return 0


def restore_backup_cmd(args) -> int:
    """Restore the memory DB from a backup file."""
    try:
        from core import backup as _bk
    except Exception as e:
        bad(f"Could not load backup module: {e}")
        return 1
    if not args:
        bad("Usage: python weaver-cli.py restore-backup <file> [--overwrite]")
        info("List available backups: python weaver-cli.py backups")
        return 1
    archive = args[0]
    overwrite = "--overwrite" in args[1:] or "-f" in args[1:]
    say("Restoring WeaverCode memory…")
    msg = _bk.restore_backup(archive, overwrite=overwrite)
    if msg.startswith("✅"):
        for line in msg.splitlines():
            ok(line.lstrip("✅ ")) if line.startswith("✅") else info(line)
        info("Restart to apply: python weaver-cli.py restart")
        return 0
    bad(msg)
    return 1


# ── logs / version / help ────────────────────────────────────────────────────
def _tail(path: Path, n: int) -> None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for l in lines[-n:]:
            print("   " + l)
    except Exception:
        info("(no log yet)")


def logs(args) -> int:
    n = 40
    if args:
        try:
            n = int(args[0])
        except ValueError:
            pass
    say(f"Last {n} log lines  ·  {LOG_FILE}")
    _tail(LOG_FILE, n)
    return 0


def version(_args=None) -> int:
    try:
        from core.ui import WEAVER_VERSION
        print(f"WeaverCode {WEAVER_VERSION}")
    except Exception:
        print("WeaverCode (version unknown)")
    print(f"Platform: {platform_name()}  ·  Python {sys.version.split()[0]}")
    return 0


def banner_cmd(_args=None) -> int:
    """Show the WeaverCode hero banner (Hello / WEAVER CODE + artwork)."""
    try:
        from core import banner
        banner.show()
    except Exception:
        say("WeaverCode 🕸️")
    return 0


def help_cmd(_args=None) -> int:
    print(__doc__)
    return 0


# ── dispatch ─────────────────────────────────────────────────────────────────
COMMANDS = {
    "install": install,
    "start": start, "up": start, "web": start,
    "stop": stop, "down": stop,
    "restart": restart, "restore": restart,
    "status": status,
    "url": url_cmd,
    "open": open_cmd,
    "update": update,
    "provider": provider_cmd,
    "key": key_cmd,
    "model": model_cmd,
    "doctor": doctor, "diagnose": doctor,
    "fix": fix,
    "backup": backup_cmd,
    "backups": backups_cmd, "list-backups": backups_cmd,
    "restore-backup": restore_backup_cmd, "restore_backup": restore_backup_cmd,
    "symbols": symbols_cmd, "symbol": symbols_cmd,
    "logs": logs,
    "banner": banner_cmd, "hello": banner_cmd,
    "version": version, "--version": version, "-v": version,
    "help": help_cmd, "--help": help_cmd, "-h": help_cmd,
}


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        return help_cmd()
    cmd = argv[0].lower()
    fn = COMMANDS.get(cmd)
    if not fn:
        bad(f"Unknown command: {cmd}")
        info("Run: python weaver-cli.py help")
        return 1
    try:
        return fn(argv[1:]) or 0
    except KeyboardInterrupt:
        print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
