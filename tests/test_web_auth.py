"""
test_web_auth.py — أمان لوحة الويب: توكن دخول اختياري لغير الاتصالات المحلية
==========================================================================
يتحقّق أنّ:
- بلا WEAVER_WEB_TOKEN → لا مصادقة (سلوك افتراضي، لا كسر).
- الاتصالات المحلية (127.0.0.1) تمرّ دائماً بلا توكن.
- الاتصالات غير المحلية تُرفض بلا توكن صحيح، وتمرّ بالكوكي/الرابط الصحيح.
لا يمسّ مفاتيح المزوّد إطلاقاً.
"""

import pytest

from web.server import Handler


def _mk(client="10.0.0.5", path="/", command="GET", cookie="", xtok=None):
    """يبني Handler وهمياً (بلا شبكة) مع تسجيل الردود."""
    h = Handler.__new__(Handler)
    h.client_address = (client, 12345)
    h.path = path
    h.command = command
    hdr = {}
    if cookie:
        hdr["Cookie"] = cookie
    if xtok is not None:
        hdr["X-Weaver-Token"] = xtok
    h.headers = hdr
    h._events = {"json": None, "login": False, "status": None, "set_cookie": None,
                 "location": None}
    h._json = lambda obj, code=200: h._events.__setitem__("json", (obj, code))
    h._login_page = lambda: h._events.__setitem__("login", True)

    def _sr(code):
        h._events["status"] = code
    def _sh(k, v):
        if k == "Set-Cookie":
            h._events["set_cookie"] = v
        if k == "Location":
            h._events["location"] = v
    h.send_response = _sr
    h.send_header = _sh
    h.end_headers = lambda: None
    return h


def test_no_token_allows_everyone(monkeypatch):
    monkeypatch.delenv("WEAVER_WEB_TOKEN", raising=False)
    assert _mk(client="10.0.0.5")._require_auth() is True   # لا توكن → مسموح


def test_local_bypasses_token(monkeypatch):
    monkeypatch.setenv("WEAVER_WEB_TOKEN", "s3cret")
    assert _mk(client="127.0.0.1")._require_auth() is True  # محلي → مسموح دائماً


def test_remote_no_token_blocked_login(monkeypatch):
    monkeypatch.setenv("WEAVER_WEB_TOKEN", "s3cret")
    h = _mk(client="10.0.0.5", path="/")
    assert h._require_auth() is False and h._events["login"] is True


def test_remote_api_no_token_401(monkeypatch):
    monkeypatch.setenv("WEAVER_WEB_TOKEN", "s3cret")
    h = _mk(client="10.0.0.5", path="/api/status")
    assert h._require_auth() is False
    assert h._events["json"] is not None and h._events["json"][1] == 401


def test_remote_wrong_cookie_blocked(monkeypatch):
    monkeypatch.setenv("WEAVER_WEB_TOKEN", "s3cret")
    h = _mk(client="10.0.0.5", cookie="weaver_token=WRONG")
    assert h._require_auth() is False


def test_remote_correct_cookie_allowed(monkeypatch):
    monkeypatch.setenv("WEAVER_WEB_TOKEN", "s3cret")
    h = _mk(client="10.0.0.5", cookie="weaver_token=s3cret")
    assert h._require_auth() is True


def test_remote_header_token_allowed(monkeypatch):
    monkeypatch.setenv("WEAVER_WEB_TOKEN", "s3cret")
    assert _mk(client="10.0.0.5", xtok="s3cret")._require_auth() is True


def test_remote_query_token_sets_cookie(monkeypatch):
    monkeypatch.setenv("WEAVER_WEB_TOKEN", "s3cret")
    h = _mk(client="10.0.0.5", path="/?token=s3cret")
    assert h._require_auth() is False          # يعيد التوجيه (لا يُكمل الطلب الحالي)
    assert h._events["status"] == 302
    assert "weaver_token=s3cret" in (h._events["set_cookie"] or "")
    assert h._events["location"] == "/"
