"""
server.py — FastAPI Dashboard لـ WeaverCode
يعمل على: http://<host>:7878  (افتراضياً 0.0.0.0 للوصول من كل الأجهزة)

مزايا:
- بثّ أحداث الوكيل الحية عبر WebSocket.
- تحميل الملفات **بلا حدّ حجم** (بثّ مباشر من القرص — يدعم 1GB فأكثر).
- إدارة المهام والمحادثات والإعدادات وGitHub من الواجهة.
- الـ daemon يعمل داخل نفس العملية ليصل بثّ الأحداث للواجهة فعلياً.
"""

import os
import sys
import json
import time
import zipfile
import tempfile
import asyncio
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    import uvicorn
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn",
                    "--break-system-packages", "-q"])
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    import uvicorn

from background.events import event_bus, WeaverEvent, EventType  # noqa: E402
from background.daemon import WeaverDaemon                        # noqa: E402
from background import status as st                               # noqa: E402

app = FastAPI(title="WeaverCode Dashboard")
BASE = Path(__file__).resolve().parent
WEAVER_ROOT = BASE.parent
DB_PATH = Path(os.path.expanduser(os.environ.get("WEAVER_DB_PATH", "~/.weaver/memory.db")))


def _outputs_dir() -> Path:
    """مجلد المخرجات القابلة للتحميل (قابل للضبط، مع بدائل حسب النظام)."""
    env = os.environ.get("WEAVER_OUTPUTS")
    if env:
        p = Path(os.path.expanduser(env))
    else:
        termux = Path(os.path.expanduser("~/storage/downloads/WeaverCode_outputs"))
        p = termux if termux.parent.exists() else Path(os.path.expanduser("~/WeaverCode_outputs"))
    p.mkdir(parents=True, exist_ok=True)
    return p


OUTPUTS = _outputs_dir()

app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")
INDEX_HTML = BASE / "templates" / "index.html"

connections = []
_daemon = WeaverDaemon()


# ── تشغيل الـ daemon داخل نفس العملية (ليصل البثّ للواجهة) ────────────────────

@app.on_event("startup")
async def _start_daemon():
    asyncio.create_task(_daemon.start())


@app.on_event("shutdown")
async def _stop_daemon():
    _daemon.stop()


# ── الصفحة الرئيسية ──────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(str(INDEX_HTML), media_type="text/html")


# ── الحالة ───────────────────────────────────────────────────────────────────

def _read_env() -> dict:
    env = {}
    env_file = WEAVER_ROOT / "config" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


@app.get("/api/status")
async def get_status():
    env = _read_env()
    stats = {"conversations": 0, "facts": 0}
    if DB_PATH.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(DB_PATH))
            stats["conversations"] = conn.execute(
                "SELECT COUNT(*) FROM conversations").fetchone()[0]
            try:
                stats["facts"] = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            except Exception:
                pass
            conn.close()
        except Exception:
            pass
    key = env.get("WEAVER_API_KEY", "").strip()
    return {
        "daemon": st.read_status(),
        "model": env.get("WEAVER_MODEL", "غير محدد"),
        "provider": env.get("WEAVER_BASE_URL", "").split("//")[-1].split("/")[0],
        "key_set": bool(key) and len(key) > 5 and "YOUR_" not in key.upper(),
        "stats": stats,
        "queue": len(st.read_queue()),
    }


# ── المهام ───────────────────────────────────────────────────────────────────

@app.post("/api/task")
async def submit_task(body: dict):
    prompt = (body.get("prompt") or "").strip()
    mode = body.get("mode", "main")
    if not prompt:
        raise HTTPException(400, "prompt مطلوب")
    position = st.queue_task(prompt, mode)
    return {"queued": True, "position": position}


# ── المحادثات ────────────────────────────────────────────────────────────────

@app.get("/api/conversations")
async def get_conversations(limit: int = 20, search: str = ""):
    if not DB_PATH.exists():
        return {"conversations": []}
    import sqlite3
    try:
        conn = sqlite3.connect(str(DB_PATH))
        if search:
            rows = conn.execute(
                "SELECT id, prompt, response, tools_used, created_at "
                "FROM conversations WHERE prompt LIKE ? OR response LIKE ? "
                "ORDER BY created_at DESC LIMIT ?",
                (f"%{search}%", f"%{search}%", limit)).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, prompt, response, tools_used, created_at "
                "FROM conversations ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return {"conversations": [
            {"id": r[0], "prompt": r[1], "response": r[2] or "",
             "tools": _safe_json(r[3]), "timestamp": r[4]} for r in rows]}
    except Exception as e:
        return {"conversations": [], "error": str(e)}


def _safe_json(s):
    try:
        return json.loads(s or "[]")
    except Exception:
        return []


# ── الملفات (تحميل بلا حدّ حجم — بثّ من القرص) ────────────────────────────────

@app.get("/api/files")
async def list_files():
    files = []
    for f in sorted(OUTPUTS.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.is_file():
            stt = f.stat()
            files.append({
                "name": f.name,
                "path": str(f.relative_to(OUTPUTS)),
                "size": stt.st_size,
                "modified": stt.st_mtime,
                "type": f.suffix.lstrip(".") or "file",
            })
    # لا استثناء على الحجم؛ حدّ عددي عالٍ لسلامة الواجهة فقط
    return {"files": files, "outputs_dir": str(OUTPUTS)}


def _safe_output_path(filepath: str) -> Path:
    """يمنع الخروج خارج مجلد المخرجات (path traversal)."""
    target = (OUTPUTS / filepath).resolve()
    if not str(target).startswith(str(OUTPUTS.resolve())):
        raise HTTPException(400, "مسار غير صالح")
    return target


@app.get("/api/files/download/{filepath:path}")
async def download_file(filepath: str):
    f = _safe_output_path(filepath)
    if not f.exists() or not f.is_file():
        raise HTTPException(404, "الملف غير موجود")
    # FileResponse يبثّ الملف على دفعات من القرص — يدعم 1GB فأكثر دون تحميله بالذاكرة
    return FileResponse(str(f), filename=f.name, media_type="application/octet-stream")


@app.get("/api/files/download-zip")
async def download_all_zip():
    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for f in OUTPUTS.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(OUTPUTS))
    return FileResponse(tmp.name, filename="WeaverCode_outputs.zip",
                        media_type="application/zip")


# ── الإعدادات ────────────────────────────────────────────────────────────────

@app.get("/api/settings")
async def get_settings():
    settings = {}
    for k, v in _read_env().items():
        if "KEY" in k and len(v) > 8:
            settings[k] = v[:8] + "···"
        else:
            settings[k] = v
    return {"settings": settings}


@app.post("/api/settings")
async def update_settings(body: dict):
    env_file = WEAVER_ROOT / "config" / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    for key, value in body.items():
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"# {key}="):
                lines[i] = f"{key}={value}"
                updated = True
                break
        if not updated:
            lines.append(f"{key}={value}")
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"updated": True}


@app.post("/api/settings/test-connection")
async def test_connection():
    result = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0,'.'); "
         "from core.engine.provider import get_provider, Message; import asyncio; "
         "p=get_provider(); "
         "r=asyncio.run(p.complete([Message(role='user',content='hi')])); "
         "print(r['choices'][0]['message'].get('content','')[:60])"],
        capture_output=True, text=True, timeout=60, cwd=str(WEAVER_ROOT))
    return {"success": result.returncode == 0,
            "output": (result.stdout.strip() or result.stderr.strip())[:500]}


# ── GitHub ───────────────────────────────────────────────────────────────────

@app.get("/api/github")
async def get_github_info():
    def _git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True,
                              cwd=str(WEAVER_ROOT)).stdout.strip()
    return {
        "commits": _git("log", "--oneline", "-5").splitlines(),
        "remote": _git("remote", "get-url", "origin"),
        "branch": _git("branch", "--show-current"),
    }


@app.post("/api/github/push")
async def github_push(body: dict):
    msg = body.get("message", "🕸️ WeaverCode update")
    branch = subprocess.run(["git", "branch", "--show-current"], capture_output=True,
                            text=True, cwd=str(WEAVER_ROOT)).stdout.strip() or "main"
    output = []
    for cmd in (["git", "add", "-A"], ["git", "commit", "-m", msg],
                ["git", "push", "origin", branch]):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(WEAVER_ROOT))
        output.append((r.stdout + r.stderr).strip())
    return {"output": "\n".join(o for o in output if o)}


# ── الأوامر السريعة ──────────────────────────────────────────────────────────

_PROVIDER_MAP = {
    "groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "openrouter": ("https://openrouter.ai/api/v1", "anthropic/claude-sonnet-4-6"),
    "anthropic": ("https://api.anthropic.com/v1", "claude-sonnet-4-6"),
    "openai": ("https://api.openai.com/v1", "gpt-4o"),
    "aerolink": ("https://capi.aerolink.lat", "claude-fable-5"),
}


@app.post("/api/command")
async def run_command(body: dict):
    cmd = (body.get("command") or "").strip()
    if cmd.startswith("/model "):
        return await update_settings({"WEAVER_MODEL": cmd[7:].strip()})
    if cmd.startswith("/key "):
        return await update_settings({"WEAVER_API_KEY": cmd[5:].strip()})
    if cmd.startswith("/provider "):
        name = cmd[10:].strip().lower()
        if name in _PROVIDER_MAP:
            url, model = _PROVIDER_MAP[name]
            return await update_settings({"WEAVER_BASE_URL": url, "WEAVER_MODEL": model})
        return {"error": f"مزوّد غير معروف: {name}"}
    if cmd == "/status":
        return await get_status()
    if cmd == "/clear":
        return await _clear_memory()
    if cmd in ("/help", "/commands"):
        return {"help": _list_commands()}
    return await submit_task({"prompt": cmd.lstrip("/"), "mode": "main"})


async def _clear_memory():
    if DB_PATH.exists():
        import sqlite3
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM conversations WHERE importance < 0.5")
        conn.commit()
        conn.close()
    return {"cleared": True}


def _list_commands():
    return [
        "/model <name>     — تغيير النموذج",
        "/key <key>        — تغيير المفتاح",
        "/provider <name>  — groq/deepseek/openrouter/anthropic/openai/aerolink",
        "/status           — حالة النظام",
        "/clear            — تنظيف الذاكرة",
        "/help             — هذه القائمة",
    ]


# ── WebSocket: البثّ الحيّ ────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connections.append(websocket)
    for event in event_bus.history[-15:]:
        await websocket.send_text(event.to_json())

    async def send_event(event: WeaverEvent):
        try:
            await websocket.send_text(event.to_json())
        except Exception:
            pass

    unsub = event_bus.subscribe(send_event)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "task":
                    st.queue_task(msg.get("prompt", ""), msg.get("mode", "main"))
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        unsub()
        if websocket in connections:
            connections.remove(websocket)


def main():
    host = os.environ.get("WEAVER_WEB_HOST", "0.0.0.0")
    port = int(os.environ.get("WEAVER_WEB_PORT", "7878"))
    print(f"🕸️ WeaverCode Dashboard — http://{host}:{port}")
    if host == "0.0.0.0":
        print("   ⚠️  متاح على شبكتك المحلية. لحصره بجهازك: WEAVER_WEB_HOST=127.0.0.1")
    uvicorn.run(app, host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
