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
import urllib.request
import urllib.error
import urllib.parse as _urlparse
import hashlib
import base64
import secrets as _secrets

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
    "nvidia": ("https://integrate.api.nvidia.com/v1", "meta/llama-3.1-70b-instruct"),
    "together": ("https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo"),
    "mistral": ("https://api.mistral.ai/v1", "mistral-large-latest"),
    "aerolink": ("https://capi.aerolink.lat", "claude-fable-5"),
}

# بادئات مفاتيح مميّزة لا لبس فيها → منصة (لكشف المنصة من المفتاح تلقائياً).
# نتجنّب البادئات الغامضة (sk- المجرّدة) حتى لا نكسر بوابة قائمة مثل aerolink.
_KEY_PREFIX_PLATFORM = [
    ("nvapi-", "nvidia"),
    ("sk-ant-", "anthropic"),
    ("sk-or-", "openrouter"),
    ("gsk_", "groq"),
]


def _platform_from_key(key: str):
    """يكشف المنصة من بادئة المفتاح → (base_url, model, name) أو None."""
    key = (key or "").strip()
    for prefix, name in _KEY_PREFIX_PLATFORM:
        if key.startswith(prefix):
            url, model = _PROVIDER_MAP[name]
            return url, model, name
    return None


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


_FILES_SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv",
               ".mypy_cache", ".pytest_cache", "dist", "build", ".next"}


def _files_root() -> Path:
    """مجلد الملفات المعروضة/القابلة للتنزيل = حيث يكتب الوكيل فعلاً.

    المستودع المستنسَخ إن اختير، وإلا مجلد المخرجات. هكذا كل ملف يُنشئه الوكيل
    (سواء مشروع محلي أو داخل مستودع) يظهر في شاشة «الملفات» ويكون قابلاً للتنزيل.
    """
    ws = _active_workspace()
    if ws.get("work_dir") and os.path.isdir(ws["work_dir"]):
        return Path(ws["work_dir"])
    return OUTPUTS


def _api_files() -> dict:
    root = _files_root()
    files = []
    for f in root.rglob("*"):
        # تخطّي مجلدات النظام/البناء الضخمة
        if any(part in _FILES_SKIP for part in f.parts):
            continue
        if f.is_file():
            try:
                stt = f.stat()
                files.append({"name": f.name, "path": str(f.relative_to(root)),
                              "size": stt.st_size, "modified": stt.st_mtime,
                              "type": f.suffix.lstrip(".") or "file"})
            except Exception:
                continue
        if len(files) >= 2000:
            break
    files.sort(key=lambda x: x["modified"], reverse=True)
    ws = _active_workspace()
    return {"files": files, "outputs_dir": str(root),
            "repo": ws.get("repo", ""), "count": len(files)}


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


def _github_token() -> str:
    """التوكن المتصل لـ GitHub (من الارتباطات)."""
    try:
        for it in _load_integrations():
            if it.get("id") == "github":
                return str(it.get("token", "")).strip()
    except Exception:
        pass
    return ""


def _http_get_json(url: str, headers=None, timeout: int = 20):
    """GET يُرجع JSON. يجرّب urllib ثم curl (Termux). يُرجع (data, error)."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), None
    except Exception:
        try:
            args = ["curl", "-sS", url, "--max-time", str(timeout)]
            for k, v in (headers or {}).items():
                args += ["-H", f"{k}: {v}"]
            out = subprocess.run(args, capture_output=True, text=True,
                                 timeout=timeout + 5)
            return json.loads(out.stdout), None
        except Exception as e:
            return None, str(e)


def _api_github_repos() -> dict:
    """قائمة مستودعات المستخدم الحقيقية من GitHub API (بلا وهم)."""
    token = _github_token()
    if not token:
        return {"connected": False, "repos": []}
    data, err = _http_get_json(
        "https://api.github.com/user/repos"
        "?per_page=100&sort=updated"
        "&affiliation=owner,collaborator,organization_member",
        {"Authorization": f"Bearer {token}",
         "Accept": "application/vnd.github+json",
         "User-Agent": "WeaverCode"})
    if err or not isinstance(data, list):
        detail = err or (data.get("message") if isinstance(data, dict) else "")
        return {"connected": True, "repos": [], "error": detail or "تعذّر جلب المستودعات"}
    repos = [{
        "full_name": r.get("full_name"),
        "name": r.get("name"),
        "private": bool(r.get("private", False)),
        "description": r.get("description") or "",
        "url": r.get("html_url"),
        "clone_url": r.get("clone_url"),
        "default_branch": r.get("default_branch", "main"),
        "updated_at": r.get("updated_at"),
        "language": r.get("language") or "",
    } for r in data if r.get("full_name")]
    return {"connected": True, "repos": repos, "count": len(repos)}


def _http_post_json(url: str, payload: dict, headers=None, timeout: int = 20):
    """POST بجسم JSON ويُرجع (data, error). urllib ثم curl (Termux)."""
    body = json.dumps(payload).encode("utf-8")
    hdrs = dict(headers or {})
    hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, body, hdrs, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8")), None
        except Exception:
            return None, f"HTTP {e.code}"
    except Exception:
        try:
            args = ["curl", "-sS", "-X", "POST", url, "--data", body.decode("utf-8"),
                    "--max-time", str(timeout)]
            for k, v in hdrs.items():
                args += ["-H", f"{k}: {v}"]
            out = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 5)
            return json.loads(out.stdout), None
        except Exception as e:
            return None, str(e)


def _api_github_create_repo(body: dict) -> dict:
    """إنشاء مستودع جديد حقيقي في حساب المستخدم عبر GitHub API."""
    token = _github_token()
    if not token:
        return {"ok": False, "error": "غير متصل بـ GitHub"}
    name = str(body.get("name", "")).strip()
    if not name:
        return {"ok": False, "error": "اسم المستودع مطلوب"}
    payload = {
        "name": name,
        "private": bool(body.get("private", True)),
        "auto_init": True,  # ينشئ فرعاً افتراضياً (main) بـ README ليكون جاهزاً
    }
    desc = str(body.get("description", "")).strip()
    if desc:
        payload["description"] = desc
    data, err = _http_post_json(
        "https://api.github.com/user/repos", payload,
        {"Authorization": f"Bearer {token}",
         "Accept": "application/vnd.github+json",
         "User-Agent": "WeaverCode"})
    if err or not isinstance(data, dict) or not data.get("full_name"):
        detail = err or (data.get("message") if isinstance(data, dict) else "")
        return {"ok": False, "error": detail or "تعذّر إنشاء المستودع"}
    return {"ok": True, "repo": {
        "full_name": data.get("full_name"),
        "name": data.get("name"),
        "private": bool(data.get("private", False)),
        "description": data.get("description") or "",
        "url": data.get("html_url"),
        "clone_url": data.get("clone_url"),
        "default_branch": data.get("default_branch", "main"),
        "language": data.get("language") or "",
    }}


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
    # auth_url = صفحة إنشاء التوكن/الاعتماد مباشرةً (خطوة «السماح» الفعلية).
    return [
        {"id": "github", "name": "GitHub", "icon": "🐙", "url": gh,
         "auth_url": "https://github.com/settings/tokens/new?description=WeaverCode&scopes=repo",
         "token": "", "enabled": True, "builtin": True},
        {"id": "colab", "name": "Google Colab", "icon": "📓", "url": colab,
         "auth_url": colab, "token": "", "enabled": True, "builtin": True},
        {"id": "canva", "name": "Canva", "icon": "🎨", "url": "https://www.canva.com",
         "auth_url": "https://www.canva.com/settings", "token": "", "enabled": True, "builtin": True},
        {"id": "vercel", "name": "Vercel", "icon": "▲", "url": "https://vercel.com/dashboard",
         "auth_url": "https://vercel.com/account/tokens", "token": "", "enabled": False, "builtin": True},
        {"id": "huggingface", "name": "Hugging Face", "icon": "🤗", "url": "https://huggingface.co",
         "auth_url": "https://huggingface.co/settings/tokens/new", "token": "", "enabled": False, "builtin": True},
        {"id": "replit", "name": "Replit", "icon": "🖥️", "url": "https://replit.com",
         "auth_url": "https://replit.com/account#connected-services", "token": "", "enabled": False, "builtin": True},
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


def _http_post_form(url: str, data: dict, timeout: int = 15) -> dict:
    """POST بصيغة form-urlencoded ويُرجع JSON (لتدفّق OAuth). fallback إلى curl."""
    body = _urlparse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url, body, {"Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        # fallback: curl (متوفّر دائماً على Termux)
        try:
            args = ["curl", "-sS", "-X", "POST", url,
                    "-H", "Accept: application/json",
                    "--data", _urlparse.urlencode(data), "--max-time", str(timeout)]
            out = subprocess.run(args, capture_output=True, text=True, timeout=timeout + 5)
            return json.loads(out.stdout)
        except Exception as e:
            return {"error": "network", "error_description": str(e)}


# إعداد OAuth الدائم (يُدار من الواجهة، محفوظ محلياً، غير مرفوع لـ git)
_OAUTH_CONFIG_FILE = WEAVER_ROOT / "config" / "oauth.json"


def _oauth_config() -> dict:
    if _OAUTH_CONFIG_FILE.exists():
        try:
            return json.loads(_OAUTH_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _oauth_config_save(cfg: dict) -> None:
    _OAUTH_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    _OAUTH_CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# معرّف تطبيق WeaverCode العام (client_id عام وآمن للنشر — ليس سرّاً).
# يتيح Device Flow لأي مستخدم دون تسجيل تطبيق خاص. يبقى قابلاً للتجاوز عبر
# .env أو إعداد الواجهة (لمن يريد تطبيقه الخاص + الضغطة الواحدة).
_DEFAULT_GH_CLIENT_ID = "Ov23liwzvdZiy6rN8J7X"


def _gh_client_id() -> str:
    # الأولوية: البيئة (.env) → إعداد الواجهة → المعرّف العام المشحون
    v = os.environ.get("GITHUB_OAUTH_CLIENT_ID", "").strip()
    if v:
        return v
    v = str(_oauth_config().get("github", {}).get("client_id", "")).strip()
    if v:
        return v
    return _DEFAULT_GH_CLIENT_ID


def _gh_client_secret() -> str:
    v = os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "").strip()
    if v:
        return v
    return str(_oauth_config().get("github", {}).get("client_secret", "")).strip()


def _gh_redirect_uri() -> str:
    return os.environ.get("GITHUB_OAUTH_REDIRECT",
                          "http://localhost:8080/oauth/callback").strip()


# حالات OAuth المؤقتة (CSRF) لتدفّق الضغطة الواحدة
_oauth_states = set()


def _api_oauth_status() -> dict:
    """يخبر الواجهة أي طرق اتصال متاحة:
    github_oneclick = زر «Allow» بضغطة واحدة (client_id + secret)
    github          = device flow (client_id فقط)"""
    cid, sec = _gh_client_id(), _gh_client_secret()
    return {"github": bool(cid), "github_oneclick": bool(cid and sec)}


def _api_oauth_config_get() -> dict:
    """يُرجع إعداد OAuth للعرض (بلا كشف السرّ)."""
    gh = _oauth_config().get("github", {})
    env_cid = bool(os.environ.get("GITHUB_OAUTH_CLIENT_ID", "").strip())
    env_sec = bool(os.environ.get("GITHUB_OAUTH_CLIENT_SECRET", "").strip())
    return {"github": {
        "client_id": _gh_client_id(),
        "has_secret": bool(_gh_client_secret()),
        "from_env": env_cid or env_sec,   # مضبوط عبر .env (لا يُعدَّل من الواجهة)
    }}


def _api_oauth_config_save(body: dict) -> dict:
    """يحفظ Client ID/Secret لخدمة في config/oauth.json (دائم، محلي).
    الافتراضي github؛ خدمات PKCE (canva...) تحفظ client_id فقط (بلا سرّ)."""
    service = str(body.get("service", "github")).strip() or "github"
    cid = str(body.get("client_id", "")).strip()
    sec = str(body.get("client_secret", "")).strip()
    cfg = _oauth_config()
    node = cfg.setdefault(service, {})
    if cid:
        node["client_id"] = cid
    if sec:  # لا نمسح السرّ إن تُرك فارغاً
        node["client_secret"] = sec
    _oauth_config_save(cfg)
    return {"saved": True, **_api_oauth_status(),
            "pkce": _api_pkce_services()}


def _api_oauth_github_authorize() -> dict:
    """يبني رابط «Authorize» لتدفّق الضغطة الواحدة (authorization code)."""
    cid = _gh_client_id()
    if not cid or not _gh_client_secret():
        return {"error": "يلزم GITHUB_OAUTH_CLIENT_ID و GITHUB_OAUTH_CLIENT_SECRET في config/.env"}
    import secrets
    state = secrets.token_urlsafe(16)
    _oauth_states.add(state)
    if len(_oauth_states) > 50:
        _oauth_states.pop()
    url = "https://github.com/login/oauth/authorize?" + _urlparse.urlencode({
        "client_id": cid, "redirect_uri": _gh_redirect_uri(),
        "scope": "repo", "state": state})
    return {"authorize_url": url}


def _oauth_github_exchange(code: str):
    """يبدّل رمز التفويض بتوكن ويحفظه. يُرجع (نجاح, تفصيل الخطأ)."""
    if not code:
        return False, "لم يصل رمز من GitHub."
    if not _gh_client_id():
        return False, "GITHUB_OAUTH_CLIENT_ID غير مضبوط في config/.env."
    if not _gh_client_secret():
        return False, "GITHUB_OAUTH_CLIENT_SECRET غير مضبوط — أضفه لـ config/.env وأعد تشغيل الخادم."
    r = _http_post_form("https://github.com/login/oauth/access_token", {
        "client_id": _gh_client_id(), "client_secret": _gh_client_secret(),
        "code": code, "redirect_uri": _gh_redirect_uri()})
    token = r.get("access_token")
    if token:
        items = _load_integrations()
        for it in items:
            if it.get("id") == "github":
                it["token"] = token
                it["enabled"] = True
        _save_integrations(items)
        return True, ""
    # رسالة GitHub الفعلية (bad_verification_code / incorrect_client_credentials / …)
    detail = r.get("error_description") or r.get("error") or "لم يُرجع GitHub توكناً."
    return False, detail


def _api_oauth_github_start() -> dict:
    """يبدأ device flow: يطلب رمز المستخدم ورابط التفويض من GitHub."""
    cid = _gh_client_id()
    if not cid:
        return {"error": "GITHUB_OAUTH_CLIENT_ID غير مضبوط في config/.env"}
    r = _http_post_form("https://github.com/login/device/code",
                        {"client_id": cid, "scope": "repo"})
    if not r.get("device_code"):
        return {"error": r.get("error_description") or r.get("error") or "فشل بدء التفويض"}
    return {
        "user_code": r.get("user_code"),
        "verification_uri": r.get("verification_uri", "https://github.com/login/device"),
        "device_code": r.get("device_code"),
        "interval": int(r.get("interval", 5)),
        "expires_in": int(r.get("expires_in", 900)),
    }


def _api_oauth_github_poll(device_code: str) -> dict:
    """يستعلم عن اكتمال التفويض؛ عند النجاح يحفظ التوكن في تكامل github."""
    cid = _gh_client_id()
    if not cid or not device_code:
        return {"error": "بيانات ناقصة"}
    r = _http_post_form(
        "https://github.com/login/oauth/access_token",
        {"client_id": cid, "device_code": device_code,
         "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
    token = r.get("access_token")
    if token:
        items = _load_integrations()
        for it in items:
            if it.get("id") == "github":
                it["token"] = token
                it["enabled"] = True
        _save_integrations(items)
        return {"connected": True}
    err = r.get("error")
    if err in ("authorization_pending", "slow_down"):
        return {"pending": True, "slow_down": err == "slow_down"}
    return {"error": r.get("error_description") or err or "لم يكتمل التفويض"}


# ══════════════════════════════════════════════════════════════════════════
# محرّك OAuth-PKCE العام — «Allow» بضغطة واحدة بلا سرّ (Canva وأمثالها)
# ══════════════════════════════════════════════════════════════════════════
# لإضافة خدمة: أضف مدخلاً هنا + client_id (عبر البيئة أو إعداد الواجهة).
# scope قابل للضبط. redirect_uri = نفس callback المحلي.
_PKCE_SERVICES = {
    "canva": {
        "authorize": "https://www.canva.com/api/oauth/authorize",
        "token": "https://api.canva.com/rest/v1/oauth/token",
        "scope": ("design:content:read design:content:write "
                  "asset:read profile:read"),
    },
    # مستقبلاً: notion / figma / linear ... بنفس النمط
}

# تفويضات PKCE المعلّقة: state → {service, verifier}
_pkce_pending = {}


def _pkce_client_id(service: str) -> str:
    """client_id لخدمة PKCE: البيئة ثم إعداد الواجهة (لا سرّ)."""
    env_key = service.upper() + "_OAUTH_CLIENT_ID"
    v = os.environ.get(env_key, "").strip()
    if v:
        return v
    return str(_oauth_config().get(service, {}).get("client_id", "")).strip()


def _pkce_gen():
    """يولّد (code_verifier, code_challenge) بصيغة S256."""
    verifier = base64.urlsafe_b64encode(_secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _api_pkce_services() -> dict:
    """يُرجع خدمات PKCE المدعومة وأيّها مُهيّأ (له client_id)."""
    return {s: {"configured": bool(_pkce_client_id(s))}
            for s in _PKCE_SERVICES}


def _api_pkce_authorize(service: str) -> dict:
    """يبدأ تدفّق PKCE: يبني رابط «Allow» ويخزّن verifier."""
    svc = _PKCE_SERVICES.get(service)
    if not svc:
        return {"error": f"خدمة PKCE غير مدعومة: {service}"}
    cid = _pkce_client_id(service)
    if not cid:
        return {"error": f"{service}: client_id غير مضبوط — أضِفه من الإعداد."}
    verifier, challenge = _pkce_gen()
    state = _secrets.token_urlsafe(16)
    _pkce_pending[state] = {"service": service, "verifier": verifier}
    if len(_pkce_pending) > 50:
        _pkce_pending.pop(next(iter(_pkce_pending)))
    url = svc["authorize"] + "?" + _urlparse.urlencode({
        "response_type": "code", "client_id": cid,
        "redirect_uri": _gh_redirect_uri(), "scope": svc["scope"],
        "code_challenge": challenge, "code_challenge_method": "S256",
        "state": state})
    return {"authorize_url": url}


def _pkce_exchange(state: str, code: str):
    """يبدّل الرمز بتوكن (PKCE، بلا سرّ) ويحفظه في تكامل الخدمة."""
    p = _pkce_pending.pop(state, None)
    if not p:
        return False, None, "state غير صالح أو منتهٍ."
    service = p["service"]
    svc = _PKCE_SERVICES.get(service, {})
    cid = _pkce_client_id(service)
    r = _http_post_form(svc.get("token", ""), {
        "grant_type": "authorization_code", "code": code,
        "client_id": cid, "redirect_uri": _gh_redirect_uri(),
        "code_verifier": p["verifier"]})
    token = r.get("access_token")
    if not token:
        return False, service, (r.get("error_description") or r.get("error")
                                or "لم تُرجع الخدمة توكناً.")
    items = _load_integrations()
    for it in items:
        if it.get("id") == service:
            it["token"] = token
            it["enabled"] = True
    _save_integrations(items)
    return True, service, ""


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


# ── مساحات عمل المستودعات (استنساخ حقيقي ليعمل الوكيل عليها) ─────────────────

_WORKSPACE_FILE = WEAVER_ROOT / "config" / "workspace.json"


def _workspaces_dir() -> Path:
    """المجلد الأب لاستنساخات المستودعات."""
    termux = Path(os.path.expanduser("~/storage/downloads/WeaverCode_repos"))
    base = termux if termux.parent.exists() else Path(os.path.expanduser("~/WeaverCode_repos"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _active_workspace() -> dict:
    """المستودع النشِط حالياً (المستنسَخ) أو {} إن لا شيء."""
    if _WORKSPACE_FILE.exists():
        try:
            d = json.loads(_WORKSPACE_FILE.read_text(encoding="utf-8"))
            if d.get("work_dir") and os.path.isdir(d["work_dir"]):
                return d
        except Exception:
            pass
    return {}


def _token_clone_url(clone_url: str, token: str) -> str:
    """يحقن التوكن في رابط الاستنساخ للمصادقة (لا يُحفَظ في .git/config)."""
    if token and clone_url.startswith("https://"):
        return "https://x-access-token:" + token + "@" + clone_url[len("https://"):]
    return clone_url


def _api_github_select_repo(body: dict) -> dict:
    """استنساخ المستودع المختار محلياً (أو تحديثه) وتعيينه مساحة العمل النشِطة.

    هذا ما يجعل «اختيار مستودع» فعّالاً: الوكيل يعمل على ملفات المستودع الحقيقية
    ثم يُرفَع إليها — بدل اختراع مسارات وهمية.
    """
    full = str(body.get("full_name", "")).strip()
    clone_url = str(body.get("clone_url", "")).strip()
    branch = str(body.get("default_branch", "") or "main").strip()
    if not full or not clone_url:
        return {"ok": False, "error": "بيانات المستودع ناقصة"}
    token = _github_token()
    dest = _workspaces_dir() / full.replace("/", "__")
    auth_url = _token_clone_url(clone_url, token)
    try:
        if (dest / ".git").is_dir():
            # موجود: حدّثه
            r = subprocess.run(["git", "-C", str(dest), "pull", auth_url, branch],
                               capture_output=True, text=True, timeout=180)
            action = "تحديث"
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run(["git", "clone", "--depth", "50", "-b", branch,
                                auth_url, str(dest)],
                               capture_output=True, text=True, timeout=300)
            if r.returncode != 0:
                # ربما الفرع غير موجود (مستودع فارغ جديد) → استنساخ بلا -b
                r = subprocess.run(["git", "clone", "--depth", "50", auth_url, str(dest)],
                                   capture_output=True, text=True, timeout=300)
            action = "استنساخ"
        if r.returncode != 0 and not (dest / ".git").is_dir():
            return {"ok": False, "error": (r.stderr or r.stdout or "فشل الاستنساخ").strip()[:300]}
        # أزل التوكن من remote المخزّن (أمان) واضبطه على الرابط النظيف
        subprocess.run(["git", "-C", str(dest), "remote", "set-url", "origin", clone_url],
                       capture_output=True, text=True)
        _WORKSPACE_FILE.write_text(json.dumps(
            {"repo": full, "work_dir": str(dest), "branch": branch,
             "clone_url": clone_url}, ensure_ascii=False), encoding="utf-8")
        # عدد الملفات (تأكيد أنه استُنسخ فعلاً)
        n = sum(1 for _ in dest.rglob("*") if _.is_file() and ".git/" not in str(_))
        return {"ok": True, "repo": full, "path": str(dest), "action": action, "files": n}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "انتهت مهلة الاستنساخ"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def _api_workspace_get() -> dict:
    ws = _active_workspace()
    return {"active": bool(ws), "repo": ws.get("repo", ""),
            "path": ws.get("work_dir", ""), "branch": ws.get("branch", "")}


def _api_workspace_clear() -> dict:
    """إلغاء المستودع النشِط → يعود الوكيل للعمل محلياً في مجلد المخرجات."""
    try:
        if _WORKSPACE_FILE.exists():
            _WORKSPACE_FILE.unlink()
    except Exception:
        pass
    return {"ok": True}


def _github_push(msg: str) -> dict:
    # يعمل على مساحة العمل النشِطة (المستودع المستنسَخ) إن وُجدت، وإلا مستودع WeaverCode.
    ws = _active_workspace()
    cwd = ws.get("work_dir") or str(WEAVER_ROOT)
    branch = subprocess.run(["git", "-C", cwd, "branch", "--show-current"],
                            capture_output=True, text=True).stdout.strip() or \
        ws.get("branch", "main")
    push_target = ["git", "-C", cwd, "push", "origin", branch]
    # للمستودعات المستنسَخة: احقن التوكن وقت الرفع فقط (لا يُخزَّن)
    if ws:
        token = _github_token()
        clone_url = ws.get("clone_url", "")
        if token and clone_url:
            push_target = ["git", "-C", cwd, "push",
                           _token_clone_url(clone_url, token), branch]
    out = []
    for cmd in (["git", "-C", cwd, "add", "-A"],
                ["git", "-C", cwd, "commit", "-m", msg],
                push_target):
        r = subprocess.run(cmd, capture_output=True, text=True)
        # لا تُظهر التوكن في المخرجات
        clean = (r.stdout + r.stderr).replace(_github_token(), "***") if _github_token() else (r.stdout + r.stderr)
        out.append(clean.strip())
    return {"output": "\n".join(o for o in out if o), "repo": ws.get("repo", "محلي")}


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


def _discover_models() -> dict:
    """اكتشاف النماذج المتاحة فعلاً من المزود الحالي عبر /models (بلا نماذج وهمية).

    EN: Query the current provider's /models endpoint and return ONLY the real
    model ids it reports. Uses the existing _http_get_json (urllib + curl
    fallback for Termux). لا يمسّ مفاتيح/اتصال provider — قراءة فقط.
    """
    env = _read_env()
    key = (env.get("WEAVER_API_KEY") or os.environ.get("WEAVER_API_KEY", "")).strip()
    base = (env.get("WEAVER_BASE_URL") or os.environ.get("WEAVER_BASE_URL", "")).strip().rstrip("/")
    if not key or not base:
        return {"error": "لم يُحدَّد مفتاح أو رابط المزود", "models": []}

    # مسارات مرشّحة: نطبّع الجذر (نزيل /v1 الأخيرة) ثم نجرّب /v1/models و/models.
    root = base[:-3].rstrip("/") if base.lower().endswith("/v1") else base
    urls = []
    for u in (root + "/v1/models", root + "/models", base + "/models"):
        if u not in urls:
            urls.append(u)

    # صيغتا المصادقة: Bearer (OpenAI-متوافق: OpenRouter/DeepSeek/Groq/Together/
    # Ollama/aerolink…) وx-api-key (Anthropic الرسمي). نجرّب الأنسب أولاً حسب
    # المضيف ثم الأخرى — فيعمل الاكتشاف مع أي منصة مهما كانت.
    _ct = {"Content-Type": "application/json", "User-Agent": "WeaverCode"}
    bearer = dict(_ct, Authorization=f"Bearer {key}")
    anthropic = dict(_ct, **{"x-api-key": key, "anthropic-version": "2023-06-01"})
    header_sets = ([anthropic, bearer] if "anthropic" in base.lower()
                   else [bearer, anthropic])

    tried = []
    last_err = ""
    for url in urls:
        for headers in header_sets:
            tried.append(url)
            data, err = _http_get_json(url, headers, timeout=15)
            if err or not isinstance(data, (dict, list)):
                last_err = err or "استجابة غير متوقعة"
                continue
            items = (data.get("data", data.get("models", []))
                     if isinstance(data, dict) else data)
            ids = []
            for m in items or []:
                if isinstance(m, str):
                    mid = m
                elif isinstance(m, dict):
                    mid = m.get("id") or m.get("name") or m.get("model") or ""
                else:
                    mid = ""
                if mid:
                    ids.append(str(mid))
            if ids:
                auth = "x-api-key" if "x-api-key" in headers else "Bearer"
                return {"models": sorted(set(ids)), "source": url,
                        "auth": auth, "count": len(set(ids))}
            if isinstance(data, dict) and data.get("error"):
                e = data["error"]
                last_err = e.get("message") if isinstance(e, dict) else str(e)
    return {"error": last_err or "لا يدعم المزوّد /models أو المفتاح خاطئ",
            "models": [], "tried": sorted(set(tried))}


def _api_settings_save(body: dict) -> dict:
    """حفظ الإعدادات في config/.env + تحديث os.environ فوراً (مزامنة).

    قائمة مسموح بها تمنع كتابة مفاتيح عشوائية. القيم الفارغة تُتجاهَل (إبقاء
    الحالي) — فلا يُمسح المفتاح/الرابط بالخطأ ولا يُكسَر اتصال المزوّد.
    """
    allowed = {"WEAVER_API_KEY", "WEAVER_BASE_URL", "WEAVER_MODEL",
               "WEAVER_MAX_TOKENS", "WEAVER_TEMPERATURE", "WEAVER_TIMEOUT"}
    updates = {k: str(v).strip() for k, v in (body or {}).items()
               if k in allowed and str(v).strip()}
    if not updates:
        return {"updated": False, "error": "لا تحديثات صالحة"}
    # كشف المنصة من بادئة المفتاح تلقائياً (nvapi-/sk-ant-/…) إن لم يُحدَّد رابط
    # صراحةً — فتغيير المفتاح لمنصة أخرى يضبط الرابط والنموذج معاً (لا يبقى معلّقاً).
    detected = None
    if "WEAVER_API_KEY" in updates and "WEAVER_BASE_URL" not in updates:
        detected = _platform_from_key(updates["WEAVER_API_KEY"])
        if detected:
            url, model, pname = detected
            cur_base = (_read_env().get("WEAVER_BASE_URL") or "").strip()
            if url != cur_base:
                updates["WEAVER_BASE_URL"] = url
                updates.setdefault("WEAVER_MODEL", model)
    _write_env(updates)
    for k, v in updates.items():
        os.environ[k] = v  # مزامنة فورية داخل عملية الخادم
    out = {"updated": True, "saved": list(updates.keys())}
    if detected and "WEAVER_BASE_URL" in updates:
        out["detected_platform"] = detected[2]
    return out


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
    root = _files_root()
    target = (root / rel).resolve()
    if not str(target).startswith(str(root.resolve())):
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
        if path == "/api/oauth/status":
            return self._json(_api_oauth_status())
        if path == "/api/oauth/config":
            return self._json(_api_oauth_config_get())
        if path == "/api/oauth/pkce/services":
            return self._json(_api_pkce_services())
        if path == "/api/oauth/pkce/authorize":
            return self._json(_api_pkce_authorize(qs.get("service", [""])[0]))
        if path == "/api/oauth/github/authorize":
            return self._json(_api_oauth_github_authorize())
        if path == "/api/oauth/github/start":
            return self._json(_api_oauth_github_start())
        if path == "/oauth/callback":
            code = qs.get("code", [""])[0]
            state = qs.get("state", [""])[0]
            gh_err = qs.get("error_description", [qs.get("error", [""])[0]])[0]
            if gh_err:
                ok, detail = False, gh_err
            elif state in _pkce_pending:
                # خدمة PKCE (Canva وأمثالها) — بلا سرّ
                ok, _svc, detail = _pkce_exchange(state, code)
            else:
                # GitHub (authorization code + secret)
                _oauth_states.discard(state)
                ok, detail = _oauth_github_exchange(code)
            if ok:
                return self._html(
                    "<div style='font-family:sans-serif;text-align:center;"
                    "padding:60px 20px;color:#e6e6e6;background:#0F0F19;"
                    "min-height:100vh'><div style='font-size:56px'>✅</div>"
                    "<h2 style='color:#22c55e'>تم الاتصال بـ GitHub بنجاح!</h2>"
                    "<p>ارجع إلى تبويب WeaverCode — ستظهر «متصل» تلقائياً.</p>"
                    "<script>setTimeout(function(){window.close()},1200)</script>"
                    "</div>")
            import html as _htmlmod
            return self._html(
                "<div style='font-family:sans-serif;text-align:center;padding:60px 20px;"
                "color:#e6e6e6;background:#0F0F19;min-height:100vh'>"
                "<div style='font-size:56px'>❌</div>"
                "<h2>تعذّر إتمام الاتصال</h2>"
                "<p style='color:#f87171;direction:ltr'>" + _htmlmod.escape(str(detail)) + "</p>"
                "<p style='color:#928a80;font-size:13px'>الأرجح: أضف "
                "GITHUB_OAUTH_CLIENT_SECRET إلى config/.env ثم <b>أعد تشغيل الخادم</b> "
                "(bash scripts/weaver-stop.sh &amp;&amp; python3 weaver.py --background).</p></div>")
        if path == "/api/settings":
            s = {}
            for k, v in _read_env().items():
                s[k] = (v[:8] + "···") if "KEY" in k and len(v) > 8 else v
            return self._json({"settings": s})
        if path == "/api/models":
            return self._json(_discover_models())
        if path == "/api/github":
            return self._json(_api_github())
        if path == "/api/github/repos":
            return self._json(_api_github_repos())
        if path == "/api/workspace":
            return self._json(_api_workspace_get())
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
            return self._json(_api_settings_save(body))
        if path == "/api/models/discover":
            return self._json(_discover_models())
        if path == "/api/settings/test-connection":
            return self._json(_test_connection())
        if path == "/api/github/push":
            return self._json(_github_push(body.get("message", "🕸️ WeaverCode update")))
        if path == "/api/github/create-repo":
            return self._json(_api_github_create_repo(body))
        if path == "/api/github/select-repo":
            return self._json(_api_github_select_repo(body))
        if path == "/api/workspace/clear":
            return self._json(_api_workspace_clear())
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
        if path == "/api/oauth/github/poll":
            return self._json(_api_oauth_github_poll((body.get("device_code") or "").strip()))
        if path == "/api/oauth/config":
            return self._json(_api_oauth_config_save(body))
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
        root = _files_root()
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
            for f in root.rglob("*"):
                if any(part in _FILES_SKIP for part in f.parts):
                    continue
                if f.is_file():
                    try:
                        zf.write(f, f.relative_to(root))
                    except Exception:
                        continue
        self._file(Path(tmp.name), "application/zip", "WeaverCode_files.zip")
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
