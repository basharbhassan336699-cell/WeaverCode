"""
test_weaver_cli.py — أداة إدارة WeaverCode عبر الأنظمة (cross-platform CLI)
=========================================================================
يتحقّق من: تحميل الوحدة، الإرسال (dispatch)، كتابة/قراءة الإعدادات (provider/
key/model)، بناء الروابط، وكشف المنصة — بلا تشغيل خادم فعلي.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("weaver_cli", ROOT / "weaver_cli.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # اعزل ملف .env في مجلد مؤقّت (لا نلمس إعدادات المستخدم)
    monkeypatch.setattr(mod, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(mod, "HOME_WEAVER", tmp_path / ".weaver")
    monkeypatch.setattr(mod, "PID_FILE", tmp_path / ".weaver" / "web.pid")
    # الملف هو مصدر الحقيقة في الاختبار: أزل متغيّرات البيئة التي قد تتجاوزه
    for k in ("WEAVER_MODEL", "WEAVER_BASE_URL", "WEAVER_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    return mod


def test_dispatch_unknown(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    assert mod.main(["definitely-not-a-command"]) == 1


def test_help_and_version(monkeypatch, tmp_path, capsys):
    mod = _load(monkeypatch, tmp_path)
    assert mod.main([]) == 0                       # no args → help
    assert mod.main(["version"]) == 0
    out = capsys.readouterr().out
    assert "WeaverCode" in out


def test_provider_sets_env(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    assert mod.main(["provider", "groq"]) == 0
    env = mod._read_env()
    assert "groq.com" in env["WEAVER_BASE_URL"]
    assert env.get("WEAVER_MODEL")


def test_key_detects_provider(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    # مفتاح بصيغة groq (gsk_) → يُكتشف المزوّد تلقائياً
    assert mod.main(["key", "gsk_" + "x" * 20]) == 0
    env = mod._read_env()
    assert env["WEAVER_API_KEY"].startswith("gsk_")
    assert "groq.com" in env.get("WEAVER_BASE_URL", "")


def test_model_sets_env(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    assert mod.main(["model", "my-model"]) == 0
    assert mod._read_env()["WEAVER_MODEL"] == "my-model"


def test_urls_and_platform(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    monkeypatch.setenv("WEAVER_WEB_PORT", "9191")
    us = mod.urls()
    assert any("9191" in u for u in us)
    assert any("127.0.0.1" in u for u in us)
    assert mod.platform_name() in ("Android (Termux)", "Windows", "macOS", "Linux")


def test_provider_bad_usage(monkeypatch, tmp_path):
    mod = _load(monkeypatch, tmp_path)
    assert mod.main(["provider"]) == 1     # missing name → error


def test_requirements_strip_inline_comments(monkeypatch, tmp_path):
    """requirements.txt فيه تعليقات داخل السطر — يجب ألّا تُمرَّر لـ pip (كانت تكسر install)."""
    mod = _load(monkeypatch, tmp_path)
    pkgs = mod._requirements()
    assert pkgs, "no packages parsed"
    for p in pkgs:
        assert "#" not in p                 # لا تعليقات
        assert p == p.strip()               # لا فراغات على الأطراف
        assert " " not in p or p.startswith("-")  # اسم حزمة واحد نظيف
