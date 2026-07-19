"""
test_web_sessions.py — اختبارات إصلاح عيب تسجيل المحادثات + الويب
=================================================================
العيب: كل رسالة داخل المحادثة كانت تُسجَّل كمحادثة منفصلة في القائمة الخارجية.
الإصلاح: محادثة واحدة = جلسة واحدة (session_id ثابت) تتراكم فيها الرسائل.
"""

import json
import os
import tempfile

import pytest


@pytest.fixture()
def mem(monkeypatch):
    """MemoryStore على قاعدة بيانات مؤقتة معزولة."""
    db = tempfile.mktemp(suffix=".db")
    monkeypatch.setenv("WEAVER_DB_PATH", db)
    from core.memory.store import MemoryStore
    return MemoryStore()


# ── العيب الأساسي: محادثة واحدة = عنصر واحد ──────────────────────────────────

def test_multi_turn_is_one_session(mem):
    sid = "s_1"
    msgs = [{"role": "user", "content": "س1"}, {"role": "assistant", "content": "ج1"}]
    mem.save_session(sid, "س1", "س1", json.dumps(msgs, ensure_ascii=False))
    msgs += [{"role": "user", "content": "س2"}, {"role": "assistant", "content": "ج2"}]
    mem.save_session(sid, "س1", "س2", json.dumps(msgs, ensure_ascii=False))
    msgs += [{"role": "user", "content": "س3"}, {"role": "assistant", "content": "ج3"}]
    mem.save_session(sid, "س1", "س3", json.dumps(msgs, ensure_ascii=False))

    sessions = mem.list_sessions()
    assert len(sessions) == 1, "يجب أن تكون محادثة واحدة لا ثلاث"
    loaded = mem.load_session(sid)
    assert len(loaded["messages"]) == 6


def test_two_separate_sessions(mem):
    mem.save_session("a", "أ", "أ", json.dumps([{"role": "user", "content": "x"}]))
    mem.save_session("b", "ب", "ب", json.dumps([{"role": "user", "content": "y"}]))
    assert len(mem.list_sessions()) == 2


def test_delete_session(mem):
    mem.save_session("d", "د", "د", json.dumps([{"role": "user", "content": "z"}]))
    assert len(mem.list_sessions()) == 1
    assert mem.delete_session("d") is True
    assert len(mem.list_sessions()) == 0


# ── طابور المهام يحمل session_id ─────────────────────────────────────────────

def test_queue_task_carries_session_id(monkeypatch, tmp_path):
    monkeypatch.setattr("background.status.QUEUE_FILE", tmp_path / "q.json")
    from background import status as st
    st.queue_task("مهمة", "main", [], "sess_xyz")
    tasks = st.read_queue()
    assert tasks[-1]["session_id"] == "sess_xyz"


# ── دوال الويب (بدون خادم) ───────────────────────────────────────────────────

def test_api_sessions_shape(mem):
    mem.save_session("w1", "عنوان", "آخر",
                     json.dumps([{"role": "user", "content": "a"},
                                 {"role": "assistant", "content": "b"}],
                                ensure_ascii=False))
    from web import server
    out = server._api_sessions()
    assert "sessions" in out
    ids = [s["id"] for s in out["sessions"]]
    assert "w1" in ids
    s = next(s for s in out["sessions"] if s["id"] == "w1")
    assert s["prompt"] == "عنوان"
    assert "timestamp" in s


def test_api_session_load_and_delete(mem):
    mem.save_session("w2", "ع", "آخر",
                     json.dumps([{"role": "user", "content": "1"},
                                 {"role": "assistant", "content": "2"}],
                                ensure_ascii=False))
    from web import server
    loaded = server._api_session("w2")
    assert len(loaded["messages"]) == 2
    assert loaded["messages"][0]["content"] == "1"
    # delete
    res = server._api_session_delete("w2")
    assert res["deleted"] is True
    assert server._api_session("w2")["messages"] == []


def test_api_sessions_search(mem):
    mem.save_session("s_a", "برمجة بايثون", "x", json.dumps([]))
    mem.save_session("s_b", "تصميم واجهة", "y", json.dumps([]))
    from web import server
    out = server._api_sessions(search="بايثون")
    ids = [s["id"] for s in out["sessions"]]
    assert "s_a" in ids and "s_b" not in ids


# ── WebFetch يعمل عبر curl (اتصال المواقع على Termux) ────────────────────────

def test_webfetch_has_curl_fallback():
    """يتأكد أن _http_get لا يعتمد على httpx حصراً (fallback إلى curl)."""
    import inspect
    from core.tools.registry import ToolRegistry
    src = inspect.getsource(ToolRegistry._http_get)
    assert "curl" in src
    assert "httpx" in src
    # _web_fetch يستدعي _http_get لا httpx مباشرة
    fetch_src = inspect.getsource(ToolRegistry._web_fetch)
    assert "_http_get" in fetch_src


# ── الاتصال الصادق بالخدمات (connected من token حقيقي فقط) ────────────────────

def test_integrations_connected_only_with_token(tmp_path, monkeypatch):
    # عزل ملف الارتباطات في مجلد مؤقت
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    # الافتراضي: لا اعتمادات → لا شيء متصل (لا حالة وهمية)
    items = server._load_integrations()
    assert all(it.get("connected") is False for it in items), \
        "يجب ألا يظهر أي ارتباط كـ متصل دون اعتماد"
    # بعد حفظ توكن حقيقي لـ github → متصل صادقاً
    server._save_integrations([{"id": "github", "name": "GitHub",
                                "url": "https://github.com",
                                "token": "ghp_real", "enabled": True, "builtin": True}])
    items2 = server._load_integrations()
    gh = next(i for i in items2 if i["id"] == "github")
    assert gh["connected"] is True
    # ارتباط بلا توكن يبقى غير متصل
    others = [i for i in items2 if i["id"] != "github"]
    assert all(i.get("connected") is False for i in others)


# ── مستعرض مستودعات GitHub الحقيقية ─────────────────────────────────────────

def test_github_repos_requires_connection(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    # بلا توكن → غير متصل، قائمة فارغة (بلا وهم)
    r = server._api_github_repos()
    assert r["connected"] is False
    assert r["repos"] == []


def test_github_repos_returns_real_list(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    server._save_integrations([{"id": "github", "name": "GitHub",
                                "url": "https://github.com",
                                "token": "ghp_real", "enabled": True, "builtin": True}])
    fake = [
        {"full_name": "bashar/proj", "name": "proj", "private": True,
         "description": "d", "html_url": "https://github.com/bashar/proj",
         "clone_url": "https://github.com/bashar/proj.git",
         "default_branch": "main", "updated_at": "2026-01-01", "language": "Python"},
        {"name": "no_full_name"},  # يُتجاهَل: بلا full_name
    ]
    monkeypatch.setattr(server, "_http_get_json", lambda *a, **k: (fake, None))
    r = server._api_github_repos()
    assert r["connected"] is True
    assert r["count"] == 1
    repo = r["repos"][0]
    assert repo["full_name"] == "bashar/proj"
    assert repo["private"] is True
    assert repo["clone_url"] == "https://github.com/bashar/proj.git"
    assert repo["default_branch"] == "main"


def test_github_repos_surfaces_api_error(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    server._save_integrations([{"id": "github", "name": "GitHub",
                                "url": "https://github.com",
                                "token": "bad", "enabled": True, "builtin": True}])
    # GitHub يعيد رسالة خطأ (dict) بدل قائمة → تُعرض بصدق
    monkeypatch.setattr(server, "_http_get_json",
                        lambda *a, **k: ({"message": "Bad credentials"}, None))
    r = server._api_github_repos()
    assert r["connected"] is True
    assert r["repos"] == []
    assert "Bad credentials" in r["error"]


def test_github_create_repo_requires_connection(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    r = server._api_github_create_repo({"name": "x"})
    assert r["ok"] is False


def test_github_create_repo_requires_name(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    server._save_integrations([{"id": "github", "name": "GitHub", "url": "https://github.com",
                                "token": "ghp_real", "enabled": True, "builtin": True}])
    r = server._api_github_create_repo({"name": "  "})
    assert r["ok"] is False


def test_github_create_repo_success(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    server._save_integrations([{"id": "github", "name": "GitHub", "url": "https://github.com",
                                "token": "ghp_real", "enabled": True, "builtin": True}])
    captured = {}

    def fake_post(url, payload, headers=None, timeout=20):
        captured["url"] = url
        captured["payload"] = payload
        return {"full_name": "bashar/new", "name": "new", "private": True,
                "html_url": "https://github.com/bashar/new",
                "clone_url": "https://github.com/bashar/new.git",
                "default_branch": "main", "description": "d"}, None

    monkeypatch.setattr(server, "_http_post_json", fake_post)
    r = server._api_github_create_repo({"name": "new", "private": True, "description": "d"})
    assert r["ok"] is True
    assert r["repo"]["full_name"] == "bashar/new"
    assert captured["url"] == "https://api.github.com/user/repos"
    assert captured["payload"]["auto_init"] is True


def test_github_create_repo_surfaces_error(tmp_path, monkeypatch):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    server._save_integrations([{"id": "github", "name": "GitHub", "url": "https://github.com",
                                "token": "ghp_real", "enabled": True, "builtin": True}])
    monkeypatch.setattr(server, "_http_post_json",
                        lambda *a, **k: ({"message": "name already exists on this account"}, None))
    r = server._api_github_create_repo({"name": "dup"})
    assert r["ok"] is False
    assert "already exists" in r["error"]


# ── تفويض GitHub الحقيقي (Device Flow) ───────────────────────────────────────

def test_oauth_status_reflects_client_id(monkeypatch, tmp_path):
    from web import server
    # المعرّف العام مشحون → device flow متاح دائماً (بلا إعداد)
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.setattr(server, "_OAUTH_CONFIG_FILE", tmp_path / "o.json")
    assert server._api_oauth_status()["github"] is True
    assert server._gh_client_id() == server._DEFAULT_GH_CLIENT_ID
    # .env يتجاوز المعرّف العام
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "Ov23custom")
    assert server._gh_client_id() == "Ov23custom"


def test_oauth_start_errors_without_client_id(monkeypatch):
    from web import server
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID", raising=False)
    r = server._api_oauth_github_start()
    assert "error" in r


def test_oauth_poll_saves_token(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "integrations.json")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cid")
    # حاكِ رد GitHub بنجاح التفويض
    monkeypatch.setattr(server, "_http_post_form",
                        lambda url, data, timeout=15: {"access_token": "gho_test123"})
    r = server._api_oauth_github_poll("devcode")
    assert r.get("connected") is True
    gh = next(i for i in server._load_integrations() if i["id"] == "github")
    assert gh["token"] == "gho_test123"
    assert gh["connected"] is True


def test_oauth_poll_pending(monkeypatch):
    from web import server
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setattr(server, "_http_post_form",
                        lambda url, data, timeout=15: {"error": "authorization_pending"})
    r = server._api_oauth_github_poll("devcode")
    assert r.get("pending") is True


# ── تفويض GitHub «Allow» بضغطة واحدة (authorization code flow) ────────────────

def test_oauth_oneclick_status(monkeypatch):
    from web import server
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cid")
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_SECRET", raising=False)
    assert server._api_oauth_status()["github_oneclick"] is False
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "sec")
    assert server._api_oauth_status()["github_oneclick"] is True


def test_oauth_authorize_url(monkeypatch):
    from web import server
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cidX")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "sec")
    r = server._api_oauth_github_authorize()
    assert "github.com/login/oauth/authorize" in r["authorize_url"]
    assert "client_id=cidX" in r["authorize_url"]


def test_oauth_exchange_saves_token(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "i.json")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "sec")
    monkeypatch.setattr(server, "_http_post_form",
                        lambda url, data, timeout=15: {"access_token": "gho_x"})
    ok, detail = server._oauth_github_exchange("code123")
    assert ok is True
    gh = next(i for i in server._load_integrations() if i["id"] == "github")
    assert gh["token"] == "gho_x" and gh["connected"] is True


def test_oauth_exchange_surfaces_github_error(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "i2.json")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "sec")
    monkeypatch.setattr(server, "_http_post_form",
                        lambda url, data, timeout=15: {"error": "bad_verification_code",
                                                       "error_description": "The code is incorrect."})
    ok, detail = server._oauth_github_exchange("badcode")
    assert ok is False and "incorrect" in detail.lower()


# ── إعداد OAuth الدائم من الواجهة (بدل تعديل .env يدوياً) ─────────────────────

def test_oauth_config_persists_and_no_leak(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_OAUTH_CONFIG_FILE", tmp_path / "oauth.json")
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_SECRET", raising=False)
    assert server._api_oauth_status()["github_oneclick"] is False
    server._api_oauth_config_save({"client_id": "Ov23x", "client_secret": "sekret"})
    assert server._api_oauth_status()["github_oneclick"] is True
    assert server._gh_client_id() == "Ov23x"
    assert server._gh_client_secret() == "sekret"
    got = server._api_oauth_config_get()["github"]
    assert got["client_id"] == "Ov23x"
    assert got["has_secret"] is True
    assert "client_secret" not in got   # لا يُكشف السرّ أبداً


def test_oauth_config_keeps_secret_when_blank(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_OAUTH_CONFIG_FILE", tmp_path / "oauth.json")
    monkeypatch.delenv("GITHUB_OAUTH_CLIENT_SECRET", raising=False)
    server._api_oauth_config_save({"client_id": "id1", "client_secret": "s1"})
    # حفظ لاحق بلا سرّ لا يمسح القديم
    server._api_oauth_config_save({"client_id": "id2", "client_secret": ""})
    assert server._gh_client_id() == "id2"
    assert server._gh_client_secret() == "s1"


def test_oauth_env_overrides_file(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_OAUTH_CONFIG_FILE", tmp_path / "oauth.json")
    server._api_oauth_config_save({"client_id": "fileid", "client_secret": "filesec"})
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "envid")
    assert server._gh_client_id() == "envid"   # .env له الأولوية


# ── محرّك OAuth-PKCE العام (Canva وأمثالها — Allow بلا سرّ) ────────────────────

def test_pkce_service_configured_via_client_id(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_OAUTH_CONFIG_FILE", tmp_path / "o.json")
    monkeypatch.delenv("CANVA_OAUTH_CLIENT_ID", raising=False)
    assert server._api_pkce_services()["canva"]["configured"] is False
    server._api_oauth_config_save({"service": "canva", "client_id": "pub"})
    assert server._api_pkce_services()["canva"]["configured"] is True


def test_pkce_authorize_builds_challenge(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_OAUTH_CONFIG_FILE", tmp_path / "o.json")
    server._api_oauth_config_save({"service": "canva", "client_id": "pubid"})
    a = server._api_pkce_authorize("canva")
    assert "code_challenge=" in a["authorize_url"]
    assert "code_challenge_method=S256" in a["authorize_url"]
    assert "client_id=pubid" in a["authorize_url"]


def test_pkce_exchange_uses_verifier_no_secret(monkeypatch, tmp_path):
    from web import server
    monkeypatch.setattr(server, "_OAUTH_CONFIG_FILE", tmp_path / "o.json")
    monkeypatch.setattr(server, "_INTEGRATIONS_FILE", tmp_path / "i.json")
    server._api_oauth_config_save({"service": "canva", "client_id": "pubid"})
    a = server._api_pkce_authorize("canva")
    state = list(server._pkce_pending.keys())[-1]
    captured = {}

    def _mock(url, data, timeout=15):
        captured.update(data)
        return {"access_token": "cv_tok"}
    monkeypatch.setattr(server, "_http_post_form", _mock)
    ok, svc, detail = server._pkce_exchange(state, "code")
    assert ok is True and svc == "canva"
    assert "code_verifier" in captured
    assert "client_secret" not in captured   # PKCE = بلا سرّ
    cv = next(i for i in server._load_integrations() if i["id"] == "canva")
    assert cv["token"] == "cv_tok" and cv["connected"] is True


def test_pkce_unknown_service(monkeypatch):
    from web import server
    r = server._api_pkce_authorize("nope")
    assert "error" in r
