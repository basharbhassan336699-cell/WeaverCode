"""
اختبارات مزامنة الطرفية ↔ الويب عبر config/.env + اكتشاف نماذج المنصة الحالية.
يعالج: الطرفية «تبقى معلّقة على المنصة السابقة» ولا تتزامن مع الويب.
"""

import importlib.util
import os
import pathlib
import sys

import pytest


@pytest.fixture
def weaver(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "weaver_mod", os.path.join(os.getcwd(), "weaver.py"))
    w = importlib.util.module_from_spec(spec)
    sys.modules["weaver_mod"] = w
    spec.loader.exec_module(w)
    # وجّه .env لمجلد مؤقت
    (tmp_path / "config").mkdir()
    monkeypatch.setattr(w, "__file__", str(tmp_path / "weaver.py"))
    return w


def test_save_env_writes_and_updates_environ(weaver, monkeypatch):
    monkeypatch.delenv("WEAVER_MODEL", raising=False)
    weaver.save_env({"WEAVER_MODEL": "cli-model"})
    envfile = pathlib.Path(weaver.__file__).parent / "config" / ".env"
    assert "WEAVER_MODEL=cli-model" in envfile.read_text()
    assert os.environ["WEAVER_MODEL"] == "cli-model"


def test_reload_env_picks_up_web_change(weaver, monkeypatch):
    """الويب غيّر .env → reload_env يحدّث os.environ (لا تبقى على القديم)."""
    envfile = pathlib.Path(weaver.__file__).parent / "config" / ".env"
    monkeypatch.setenv("WEAVER_API_KEY", "oldkey")
    monkeypatch.setenv("WEAVER_MODEL", "old-model")
    envfile.write_text("WEAVER_API_KEY=newkey\nWEAVER_MODEL=new-model\n")
    changed = weaver.reload_env()
    assert changed.get("WEAVER_API_KEY") == "newkey"
    assert os.environ["WEAVER_MODEL"] == "new-model"


def test_reload_env_no_change_returns_empty(weaver, monkeypatch):
    envfile = pathlib.Path(weaver.__file__).parent / "config" / ".env"
    monkeypatch.setenv("WEAVER_MODEL", "same")
    envfile.write_text("WEAVER_MODEL=same\n")
    assert weaver.reload_env() == {}


def test_reload_env_ignores_non_sync_keys(weaver, monkeypatch):
    envfile = pathlib.Path(weaver.__file__).parent / "config" / ".env"
    envfile.write_text("SOME_RANDOM=xyz\nWEAVER_MODEL=m\n")
    monkeypatch.delenv("WEAVER_MODEL", raising=False)
    weaver.reload_env()
    assert os.environ.get("SOME_RANDOM") != "xyz"  # لا يُزامَن إلا مفاتيح WEAVER_


def test_sync_provider_from_env(weaver, monkeypatch):
    monkeypatch.setenv("WEAVER_API_KEY", "k2")
    monkeypatch.setenv("WEAVER_BASE_URL", "https://new/v1")
    monkeypatch.setenv("WEAVER_MODEL", "m2")

    class _Cfg:
        api_key = "k1"; base_url = "https://old/v1"; model = "m1"; max_tokens = 8192

    class _Prov:
        config = _Cfg()

    p = _Prov()
    assert weaver._sync_provider_from_env(p) is True
    assert p.config.model == "m2" and p.config.base_url == "https://new/v1"
    # استدعاء ثانٍ بلا تغيير → False
    assert weaver._sync_provider_from_env(p) is False


def test_provider_map_has_common_platforms(weaver):
    for name in ("anthropic", "openai", "openrouter", "groq", "ollama",
                 "aerolink", "nvidia"):
        assert name in weaver._PROVIDER_MAP


def test_platform_from_key_detects_nvidia(weaver):
    d = weaver._platform_from_key("nvapi-CzABC123")
    assert d is not None
    url, model, name = d
    assert name == "nvidia" and "nvidia.com" in url


def test_platform_from_key_unambiguous_prefixes(weaver):
    assert weaver._platform_from_key("sk-ant-x")[2] == "anthropic"
    assert weaver._platform_from_key("sk-or-x")[2] == "openrouter"
    assert weaver._platform_from_key("gsk_x")[2] == "groq"


def test_platform_from_key_ambiguous_returns_none(weaver):
    # sk- المجرّدة ومفاتيح البوابات لا تُبدّل الرابط (حماية aerolink)
    assert weaver._platform_from_key("sk-plainopenai") is None
    assert weaver._platform_from_key("aerolink-random-key") is None
