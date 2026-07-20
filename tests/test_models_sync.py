"""
اختبارات اكتشاف النماذج المتاحة فعلاً + مزامنة الإعدادات (web ↔ config/.env).
"""

import os
import pathlib


def _fresh_server(tmp_path, monkeypatch, env_text=""):
    from web import server
    monkeypatch.setattr(server, "WEAVER_ROOT", tmp_path)
    (tmp_path / "config").mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / ".env").write_text(env_text, encoding="utf-8")
    return server


# ── اكتشاف النماذج ──────────────────────────────────────────────────────────

def test_discover_models_returns_real_only(tmp_path, monkeypatch):
    server = _fresh_server(
        tmp_path, monkeypatch,
        "WEAVER_API_KEY=sk-x\nWEAVER_BASE_URL=https://capi.aerolink.lat/v1\n")
    monkeypatch.setattr(server, "_http_get_json",
                        lambda *a, **k: ({"data": [{"id": "claude-fable-5"},
                                                   {"id": "gpt-4o"}]}, None))
    r = server._discover_models()
    assert r["models"] == ["claude-fable-5", "gpt-4o"]
    assert r["count"] == 2


def test_discover_models_supports_name_and_string(tmp_path, monkeypatch):
    server = _fresh_server(
        tmp_path, monkeypatch,
        "WEAVER_API_KEY=sk-x\nWEAVER_BASE_URL=https://x/v1\n")
    monkeypatch.setattr(server, "_http_get_json",
                        lambda *a, **k: ({"models": ["m1", {"name": "m2"}]}, None))
    r = server._discover_models()
    assert set(r["models"]) == {"m1", "m2"}


def test_discover_models_no_key(tmp_path, monkeypatch):
    server = _fresh_server(tmp_path, monkeypatch, "WEAVER_BASE_URL=\n")
    monkeypatch.delenv("WEAVER_API_KEY", raising=False)
    monkeypatch.delenv("WEAVER_BASE_URL", raising=False)
    r = server._discover_models()
    assert "error" in r and r["models"] == []


def test_discover_models_provider_unsupported(tmp_path, monkeypatch):
    server = _fresh_server(
        tmp_path, monkeypatch,
        "WEAVER_API_KEY=sk-x\nWEAVER_BASE_URL=https://x/v1\n")
    monkeypatch.setattr(server, "_http_get_json", lambda *a, **k: (None, "HTTP 404"))
    r = server._discover_models()
    assert "error" in r and r["models"] == []


def test_discover_models_universal_anthropic_xapikey(tmp_path, monkeypatch):
    """Anthropic الرسمي: يعمل عبر x-api-key حتى لو فشل Bearer (اكتشاف كوني)."""
    server = _fresh_server(
        tmp_path, monkeypatch,
        "WEAVER_API_KEY=sk-ant\nWEAVER_BASE_URL=https://api.anthropic.com\n")

    def http(url, headers=None, timeout=15):
        if "x-api-key" in (headers or {}) and url.endswith("/v1/models"):
            return {"data": [{"id": "claude-opus-4-8"}]}, None
        return None, "HTTP 401"

    monkeypatch.setattr(server, "_http_get_json", http)
    r = server._discover_models()
    assert r["models"] == ["claude-opus-4-8"]
    assert r["auth"] == "x-api-key"


def test_discover_models_universal_bearer_openrouter(tmp_path, monkeypatch):
    server = _fresh_server(
        tmp_path, monkeypatch,
        "WEAVER_API_KEY=sk-or\nWEAVER_BASE_URL=https://openrouter.ai/api/v1\n")

    def http(url, headers=None, timeout=15):
        if ("Bearer" in (headers or {}).get("Authorization", "")
                and url == "https://openrouter.ai/api/v1/models"):
            return {"data": [{"id": "openai/gpt-4o"}]}, None
        return None, "HTTP 404"

    monkeypatch.setattr(server, "_http_get_json", http)
    r = server._discover_models()
    assert r["models"] == ["openai/gpt-4o"]
    assert r["source"] == "https://openrouter.ai/api/v1/models"


# ── مزامنة الإعدادات ────────────────────────────────────────────────────────

def test_settings_save_allowlist_and_env(tmp_path, monkeypatch):
    server = _fresh_server(tmp_path, monkeypatch, "")
    monkeypatch.delenv("WEAVER_MODEL", raising=False)
    r = server._api_settings_save({"WEAVER_MODEL": "m", "EVIL": "x",
                                   "WEAVER_MAX_TOKENS": "16384"})
    assert set(r["saved"]) == {"WEAVER_MODEL", "WEAVER_MAX_TOKENS"}
    assert "EVIL" not in r["saved"]
    # كُتب في .env
    envfile = (tmp_path / "config" / ".env").read_text()
    assert "WEAVER_MODEL=m" in envfile
    # وحُدِّث os.environ فوراً (مزامنة)
    assert os.environ.get("WEAVER_MODEL") == "m"


def test_settings_save_nvidia_key_switches_base_url(tmp_path, monkeypatch):
    """حفظ مفتاح NVIDIA (nvapi-) يضبط الرابط والنموذج تلقائياً (لا يبقى معلّقاً)."""
    server = _fresh_server(
        tmp_path, monkeypatch,
        "WEAVER_BASE_URL=https://capi.aerolink.lat\nWEAVER_API_KEY=old\n")
    for k in ("WEAVER_BASE_URL", "WEAVER_MODEL", "WEAVER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    r = server._api_settings_save({"WEAVER_API_KEY": "nvapi-Cz123"})
    assert r["detected_platform"] == "nvidia"
    env = server._read_env()
    assert "nvidia.com" in env["WEAVER_BASE_URL"]
    assert env["WEAVER_MODEL"]


def test_settings_save_ambiguous_key_keeps_base_url(tmp_path, monkeypatch):
    """مفتاح غامض (sk-) لا يبدّل رابط بوابة قائمة مثل aerolink."""
    server = _fresh_server(
        tmp_path, monkeypatch,
        "WEAVER_BASE_URL=https://capi.aerolink.lat\n")
    monkeypatch.delenv("WEAVER_BASE_URL", raising=False)
    r = server._api_settings_save({"WEAVER_API_KEY": "sk-plainkey123"})
    assert "detected_platform" not in r
    assert server._read_env()["WEAVER_BASE_URL"] == "https://capi.aerolink.lat"


def test_settings_save_ignores_empty_no_wipe(tmp_path, monkeypatch):
    """قيمة فارغة لا تُكتب — فلا يُمحى المفتاح/الرابط بالخطأ."""
    server = _fresh_server(
        tmp_path, monkeypatch, "WEAVER_API_KEY=keepme\n")
    r = server._api_settings_save({"WEAVER_API_KEY": "   "})
    assert r["updated"] is False
    assert "WEAVER_API_KEY=keepme" in (tmp_path / "config" / ".env").read_text()


def test_daemon_reload_env_picks_up_changes(tmp_path, monkeypatch):
    """الـ daemon يلتقط تغييرات .env (مزامنة الويب ← الخادم الخلفي)."""
    import background.daemon as daemon
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / ".env").write_text('WEAVER_MODEL=from-web\nWEAVER_API_KEY="q"\n')
    # اجعل daemon يقرأ من tmp
    monkeypatch.setattr(daemon, "__file__", str(tmp_path / "background" / "daemon.py"))
    (tmp_path / "background").mkdir()
    monkeypatch.delenv("WEAVER_MODEL", raising=False)
    daemon._reload_env()
    assert os.environ.get("WEAVER_MODEL") == "from-web"
    assert os.environ.get("WEAVER_API_KEY") == "q"  # اقتُصّت علامات الاقتباس
