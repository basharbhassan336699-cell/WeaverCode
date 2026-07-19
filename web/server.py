"""
server.py — WeaverCode Dashboard بخادم مدمج (بلا أي تبعيات خارجية).
================================================================

مبني على مكتبة بايثون القياسية فقط (http.server) — يعمل على Termux/أندرويد
دون الحاجة لـ fastapi/pydantic/Rust. البثّ الحيّ عبر SSE (Server-Sent Events).

التشغيل:  python3 web/server.py   →   http://<host>:8080
"""

import os
import sys
import json
import time
import queue
import zipfile
import tempfile
import threading
import asyncio
import subprocess
import mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from background.events import event_bus, WeaverEvent  # noqa: E402
from background.daemon import WeaverDaemon              # noqa: E402
from background import status as st                     # noqa: E402

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
INDEX_HTML = BASE / "templates" / "index.html"
WEAVER_ROOT = BASE.parent
UPLOADS = WEAVER_ROOT / "uploads"


def _load_dotenv():
    """تحميل config/.env إلى البيئة حتى يعمل الـ daemon بمفتاح المستخدم عند
    تشغيل الخادم مباشرةً (scripts/weaver-bg.sh) لا عبر weaver.py فقط."""
    f = WEAVER_ROOT / "config" / ".env"
    if not f.exists():
        return
    for raw in f.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        if k:
            os.environ.setdefault(k, v)


_load_dotenv()
DB_PATH = Path(os.path.expanduser(os.environ.get("WEAVER_DB_PATH", "~/.weaver/memory.db")))

# ── عملاء SSE (كل عميل طابور آمن بين الخيوط) ──────────────────────────────────
_sse_clients = []
_sse_lock = threading.Lock()


def _outputs_dir() -> Path:
    env = os.environ.get("WEAVER_OUTPUTS")
    if env:
        p = Path(os.path.expanduser(env))
    else:
        termux = Path(os.path.expanduser("~/storage/downloads/WeaverCode_outputs"))
        p = termux if termux.parent.exists() else Path(os.path.expanduser("~/WeaverCode_outputs"))
    p.mkdir(parents=True, exist_ok=True)
    return p


OUTPUTS = _outputs_dir()

_PROVIDER_MAP = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "openrouter": ("https://openrouter.ai/api/v1", "anthropic/claude-sonnet-4-6"),
    "anthropic": ("https://api.anthropic.com/v1", "claude-sonnet-4-6"),
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
    "aerolink": ("https://capi.aerolink.lat", "claude-fable-5"),
}


# ── مساعدات البيانات ──────────────────────────────────────────────────────────

def _read_env() -> dict:
    env = {}
    f = WEAVER_ROOT / "config" / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def _write_env(updates: dict):
    f = WEAVER_ROOT / "config" / ".env"
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    for key, value in updates.items():
        done = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                lines[i] = f"{key}={value}"
                done = True
                break
        if not done:
            lines.append(f"{key}={value}")
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _stats() -> dict:
    out = {"conversations": 0, "facts": 0}
    if DB_PATH.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(DB_PATH))
            out["conversations"] = conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            try:
                out["facts"] = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            except Exception:
                pass
            conn.close()
        except Exception:
            pass
    return out


def _api_commands() -> dict:
    """قائمة أوامر السلاش مع أوصافها (للإكمال التلقائي في الواجهة)."""
    try:
        from core.commands import SlashCommands
        return {"commands": SlashCommands().list_meta()}
    except Exception:
        return {"commands": []}


def _api_status() -> dict:
    env = _read_env()
    key = env.get("WEAVER_API_KEY", "").strip()
    return {
        "daemon": st.read_status(),
        "model": env.get("WEAVER_MODEL", "غير محدد"),
        "provider": env.get("WEAVER_BASE_URL", "").split("//")[-1].split("/")[0],
        "key_set": bool(key) and len(key) > 5 and "YOUR_" not in key.upper(),
        "stats": _stats(),
        "queue": len(st.read_queue()),
    }


def _api_files() -> dict:
    files = []
    for f in sorted(OUTPUTS.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file():
            stt = f.stat()
            files.append({"name": f.name, "path": str(f.relative_to(OUTPUTS)),
                          "size": stt.st_size, "modified": stt.st_mtime,
                          "type": f.suffix.lstrip(".") or "file"})
    return {"files": files, "outputs_dir": str(OUTPUTS)}


def _api_conversations(limit=20, search="") -> dict:
    if not DB_PATH.exists():
        return {"conversations": []}
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH))
        if search:
            rows = conn.execute(
                "SELECT id,prompt,response,tools_used,created_at FROM conversations "
                "WHERE prompt LIKE ? OR response LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{search}%", f"%{search}%", limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT id,prompt,response,tools_used,created_at FROM conversations "
                "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return {"conversations": [
            {"id": r[0], "prompt": r[1], "response": r[2] or "",
             "tools": _safe_json(r[3]), "timestamp": r[4]} for r in rows]}
    except Exception as e:
        return {"conversations": [], "error": str(e)}


def _api_sessions(limit=100, search="") -> dict:
    """قائمة المحادثات كجلسات (محادثة واحدة = عنصر واحد، لا رسالة منفصلة)."""
    try:
        from core.memory.store import MemoryStore
        sessions = MemoryStore().list_sessions(limit=limit)
    except Exception as e:
        return {"sessions": [], "error": str(e)}
    if search:
        s = search.lower()
        sessions = [x for x in sessions
                    if s in (x.get("name", "") or "").lower()
                    or s in (x.get("last_prompt", "") or "").lower()]
    return {"sessions": [
        {"id": x["id"], "prompt": x.get("name") or x.get("last_prompt") or "محادثة",
         "last_prompt": x.get("last_prompt", ""),
         "timestamp": x.get("updated_at", 0)} for x in sessions]}


def _api_session(session_id: str) -> dict:
    """تحميل محادثة كاملة برسائلها (لفتحها)."""
    try:
        from core.memory.store import MemoryStore
        data = MemoryStore().load_session(session_id)
        if not data:
            return {"error": "لم تُوجد المحادثة", "messages": []}
        return {"id": data["id"], "name": data.get("name", ""),
                "messages": data.get("messages", [])}
    except Exception as e:
        return {"error": str(e), "messages": []}


def _api_session_delete(session_id: str) -> dict:
    """حذف محادثة."""
    try:
        from core.memory.store import MemoryStore
        ok = MemoryStore().delete_session(session_id)
        return {"deleted": ok}
    except Exception as e:
        return {"deleted": False, "error": str(e)}


def _safe_json(s):
    try:
        return json.loads(s or "[]")
    except Exception:
        return []


def _git(*a):
    return subprocess.run(["git", *a], capture_output=True, text=True,
                          cwd=str(WEAVER_ROOT)).stdout.strip()


def _api_github() -> dict:
    return {"commits": _git("log", "--oneline", "-5").splitlines(),
            "remote": _git("remote", "get-url", "origin"),
            "branch": _git("branch", "--show-current")}


# ── الارتباطات (Integrations) ────────────────────────────────────────────────

_INTEGRATIONS_FILE = WEAVER_ROOT / "config" / "integrations.json"


def _repo_slug() -> str:
    """استخراج owner/repo من عنوان git remote (إن وُجد)."""
    remote = _git("remote", "get-url", "origin")
    import re
    m = re.search(r"github\.com[:/]+([^/]+/[^/.\s]+)", remote or "")
    return m.group(1) if m else ""


def _default_integrations() -> list:
    """ارتباطات افتراضية متناسقة، مع اشتقاق روابط GitHub/Colab من المستودع."""
    slug = _repo_slug()
    gh = f"https://github.com/{slug}" if slug else "https://github.com"
    colab = (f"https://colab.research.google.com/github/{slug}"
             if slug else "https://colab.research.google.com")
    return [
        {"id": "github", "name": "GitHub", "icon": "🐙", "url": gh,
         "token": "", "enabled": True, "builtin": True},
        {"id": "colab", "name": "Google Colab", "icon": "📓", "url": colab,
         "token": "", "enabled": True, "builtin": True},
        {"id": "canva", "name": "Canva", "icon": "🎨", "url": "https://www.canva.com",
         "token": "", "enabled": True, "builtin": True},
        {"id": "vercel", "name": "Vercel", "icon": "▲", "url": "https://vercel.com/dashboard",
         "token": "", "enabled": False, "builtin": True},
        {"id": "huggingface", "name": "Hugging Face", "icon": "🤗", "url": "https://huggingface.co",
         "token": "", "enabled": False, "builtin": True},
        {"id": "replit", "name": "Replit", "icon": "🖥️", "url": "https://replit.com",
         "token": "", "enabled": False, "builtin": True},
    ]


def _load_integrations() -> list:
    """يدمج المحفوظ مع الافتراضي (يحدّث الروابط المشتقّة، ويبقي إعدادات المستخدم)."""
    saved = {}
    if _INTEGRATIONS_FILE.exists():
        try:
            data = json.loads(_INTEGRATIONS_FILE.read_text(encoding="utf-8"))
            for it in data.get("integrations", []):
                if it.get("id"):
                    saved[it["id"]] = it
        except Exception:
            pass
    result = []
    seen = set()
    for d in _default_integrations():
        s = saved.get(d["id"], {})
        merged = {**d, **{k: v for k, v in s.items() if k in ("url", "token", "enabled", "name", "icon")}}
        # حالة الاتصال الصادقة: متصل فقط إذا وُجد اعتماد (token) حقيقي
        merged["connected"] = bool(str(merged.get("token", "")).strip())
        result.append(merged)
        seen.add(d["id"])
    # ارتباطات مخصّصة أضافها المستخدم
    for iid, it in saved.items():
        if iid not in seen:
            it.setdefault("builtin", False)
            it["connected"] = bool(str(it.get("token", "")).strip())
            result.append(it)
    return result


def _save_integrations(items: list) -> None:
    _INTEGRATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    clean = []
    for it in items:
        if not it.get("id") or not it.get("name"):
            continue
        clean.append({
            "id": str(it["id"])[:40],
            "name": str(it["name"])[:40],
            "icon": str(it.get("icon", "🔗"))[:8],
            "url": str(it.get("url", ""))[:500],
            "token": str(it.get("token", ""))[:500],
            "enabled": bool(it.get("enabled", True)),
            "builtin": bool(it.get("builtin", False)),
        })
    _INTEGRATIONS_FILE.write_text(
        json.dumps({"integrations": clean}, ensure_ascii=False, indent=2), encoding="utf-8")


def _github_push(msg: str) -> dict:
    branch = _git("branch", "--show-current") or "main"
    out = []
    for cmd in (["git", "add", "-A"], ["git", "commit", "-m", msg],
                ["git", "push", "origin", branch]):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WEAVER_ROOT))
        out.append((r.stdout + r.stderr).strip())
    return {"output": "\n".join(o for o in out if o)}


def _test_connection() -> dict:
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.'); "
         "from core.engine.provider import get_provider, Message; import asyncio; "
         "p=get_provider(); "
         "r=asyncio.run(p.complete([Message(role='user',content='hi')])); "
         "print(r['choices'][0]['message'].get('content','')[:60])"],
        capture_output=True, text=True, timeout=60, cwd=str(WEAVER_ROOT))
    return {"success": r.returncode == 0,
            "output": (r.stdout.strip() or r.stderr.strip())[:500]}


def _run_command(cmd: str) -> dict:
    cmd = (cmd or "").strip()
    if cmd.startswith("/model "):
        _write_env({"WEAVER_MODEL": cmd[7:].strip()}); return {"updated": True}
    if cmd.startswith("/key "):
        _write_env({"WEAVER_API_KEY": cmd[5:].strip()}); return {"updated": True}
    if cmd.startswith("/provider "):
        name = cmd[10:].strip().lower()
        if name in _PROVIDER_MAP:
            url, model = _PROVIDER_MAP[name]
            _write_env({"WEAVER_BASE_URL": url, "WEAVER_MODEL": model})
            return {"updated": True}
        return {"error": f"مزوّد غير معروف: {name}"}
    if cmd == "/status":
        return _api_status()
    if cmd in ("/help", "/commands"):
        return {"help": ["/model <name>", "/key <key>", "/provider <name>",
                         "/status", "/help"]}
    pos = st.queue_task(cmd.lstrip("/"), "main")
    return {"queued": True, "position": pos}


def _save_upload(body: dict) -> dict:
    """حفظ ملف مرفوع (base64) في مجلد uploads ليقرأه الوكيل. يُرجع المسار."""
    import base64
    name = (body.get("name") or "file").replace("/", "_").replace("\\", "_")[:120]
    data = body.get("data_base64") or ""
    if "," in data and data.strip().startswith("data:"):
        data = data.split(",", 1)[1]  # إزالة بادئة data URL
    try:
        raw = base64.b64decode(data)
    except Exception:
        return {"error": "بيانات غير صالحة"}
    UPLOADS.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS / name
    # تفادي الكتابة فوق ملف موجود
    i = 1
    while dest.exists():
        dest = UPLOADS / (dest.stem + f"_{i}" + dest.suffix)
        i += 1
    dest.write_bytes(raw)
    return {"ok": True, "name": dest.name, "path": str(dest), "size": len(raw)}


def _safe_output_path(rel: str):
    target = (OUTPUTS / rel).resolve()
    if not str(target).startswith(str(OUTPUTS.resolve())):
        return None
    return target


# ── معالج HTTP ────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # -- أدوات إرسال --
    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, html: str, code=200):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type=None, download_name=None):
        size = path.stat().st_size
        ctype = content_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        # منع تخزين الواجهة في كاش المتصفح حتى تتطابق دائماً مع الخادم
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
        self.send_header("Pragma", "no-cache")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.end_headers()
        # بثّ على دفعات 1MB — يدعم ملفات ضخمة (1GB+) دون تحميلها بالذاكرة
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw or b"{}")
        except Exception:
            return {}

    # -- GET --
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/":
            # حقن رمز كسر الكاش (الإصدار) لإجبار المتصفّح على تحميل أحدث JS/CSS
            try:
                from core.ui import get_version
                bust = get_version().replace("·", "-").replace(" ", "")
            except Exception:
                bust = str(int(time.time()))
            try:
                html = INDEX_HTML.read_text(encoding="utf-8").replace(
                    "__CACHEBUST__", bust)
                return self._html(html)
            except Exception:
                return self._file(INDEX_HTML, "text/html; charset=utf-8")
        if path.startswith("/static/"):
            f = (STATIC / path[len("/static/"):]).resolve()
            if str(f).startswith(str(STATIC.resolve())) and f.is_file():
                return self._file(f)
            return self._json({"error": "not found"}, 404)
        if path == "/events":
            return self._sse()
        if path == "/api/version":
            try:
                from core.ui import WEAVER_VERSION
            except Exception:
                WEAVER_VERSION = "?"
            return self._json({"version": WEAVER_VERSION})
        if path == "/api/commands":
            return self._json(_api_commands())
        if path == "/api/status":
            return self._json(_api_status())
        if path == "/api/files":
            return self._json(_api_files())
        if path == "/api/conversations":
            limit = int(qs.get("limit", ["20"])[0])
            search = qs.get("search", [""])[0]
            return self._json(_api_conversations(limit, search))
        if path == "/api/sessions":
            limit = int(qs.get("limit", ["100"])[0])
            search = qs.get("search", [""])[0]
            return self._json(_api_sessions(limit, search))
        if path == "/api/session":
            return self._json(_api_session(qs.get("id", [""])[0]))
        if path == "/api/settings":
            s = {}
            for k, v in _read_env().items():
                s[k] = (v[:8] + "···") if "KEY" in k and len(v) > 8 else v
            return self._json({"settings": s})
        if path == "/api/github":
            return self._json(_api_github())
        if path == "/api/integrations":
            return self._json({"integrations": _load_integrations()})
        if path == "/api/files/download-zip":
            return self._zip()
        if path.startswith("/api/files/download/"):
            rel = unquote(path[len("/api/files/download/"):])
            target = _safe_output_path(rel)
            if target is None:
                return self._json({"error": "مسار غير صالح"}, 400)
            if not target.exists() or not target.is_file():
                return self._json({"error": "الملف غير موجود"}, 404)
            return self._file(target, "application/octet-stream", target.name)
        return self._json({"error": "not found"}, 404)

    # -- POST --
    def do_POST(self):
        path = urlparse(self.path).path
        body = self._read_body()
        if path == "/api/task":
            prompt = (body.get("prompt") or "").strip()
            if not prompt:
                return self._json({"error": "prompt مطلوب"}, 400)
            history = body.get("history")
            if not isinstance(history, list):
                history = []
            session_id = (body.get("session_id") or "").strip()
            pos = st.queue_task(prompt, body.get("mode", "main"), history[-20:],
                                session_id)
            return self._json({"queued": True, "position": pos})
        if path == "/api/command":
            return self._json(_run_command(body.get("command", "")))
        if path == "/api/settings":
            _write_env(body)
            return self._json({"updated": True})
        if path == "/api/settings/test-connection":
            return self._json(_test_connection())
        if path == "/api/github/push":
            return self._json(_github_push(body.get("message", "🕸️ WeaverCode update")))
        if path == "/api/integrations":
            items = body.get("integrations", [])
            if isinstance(items, list):
                _save_integrations(items)
                return self._json({"integrations": _load_integrations()})
            return self._json({"error": "صيغة غير صالحة"}, 400)
        if path == "/api/upload":
            return self._json(_save_upload(body))
        if path == "/api/session/delete":
            return self._json(_api_session_delete((body.get("id") or "").strip()))
        return self._json({"error": "not found"}, 404)

    # -- SSE (البثّ الحيّ) --
    def _sse(self):
        q = queue.Queue()
        with _sse_lock:
            _sse_clients.append(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            # إعادة إرسال آخر الأحداث للعميل الجديد
            for ev in list(event_bus.history)[-15:]:
                self._sse_write(ev.to_dict())
            while True:
                try:
                    data = q.get(timeout=15)
                    self._sse_write(data)
                except queue.Empty:
                    # نبضة إبقاء الاتصال حيّاً
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with _sse_lock:
                if q in _sse_clients:
                    _sse_clients.remove(q)

    def _sse_write(self, data: dict):
        payload = "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"
        self.wfile.write(payload.encode("utf-8"))
        self.wfile.flush()

    def _zip(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for f in OUTPUTS.rglob("*"):
                if f.is_file():
                    zf.write(f, f.relative_to(OUTPUTS))
        self._file(Path(tmp.name), "application/zip", "WeaverCode_outputs.zip")
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# ── جسر الأحداث: من حلقة الـ daemon (async) إلى عملاء SSE (خيوط) ──────────────

async def _event_bridge(event: WeaverEvent):
    data = event.to_dict()
    with _sse_lock:
        clients = list(_sse_clients)
    for q in clients:
        try:
            q.put_nowait(data)
        except Exception:
            pass


def _start_daemon_thread():
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        event_bus.subscribe(_event_bridge)
        daemon = WeaverDaemon()
        try:
            loop.run_until_complete(daemon.start())
        except Exception:
            pass
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def main():
    host = os.environ.get("WEAVER_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEAVER_WEB_PORT", "8080"))
    try:
        from core.ui import WEAVER_VERSION
    except Exception:
        WEAVER_VERSION = "?"
    _start_daemon_thread()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"🕸️ WeaverCode Dashboard {WEAVER_VERSION} — http://{host}:{port}")
    if host == "0.0.0.0":
        print("   ⚠️  متاح على شبكتك المحلية. لحصره بجهازك: WEAVER_WEB_HOST=127.0.0.1")
    print("   (خادم مدمج بلا تبعيات — يعمل على Termux مباشرةً)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
