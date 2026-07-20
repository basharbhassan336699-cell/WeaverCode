"""
providers.py — سجل مزوّدين مدفوع بالبيانات + كشف المنصة تلقائياً من المفتاح
==========================================================================

حل عام لا يخصّ منصة بعينها: أي منصة تُدخل مفتاحها يُكتشف رابطها وتُعرَض نماذجها.

آليتان متكاملتان:
  1) كشف بالبادئة  — للمنصات ذات بادئة مفتاح مميّزة (nvapi-/sk-ant-/gsk_/…).
  2) سبر تلقائي    — يجرّب نقاط /models لمزوّدي السجل بالمفتاح؛ أول من يُرجع
                     نماذج = المنصة. يغطّي المنصات ذات المفاتيح العامة (sk-…).

السجل **مدفوع بالبيانات**: افتراضي مدمج + `config/providers.json` قابل للتوسيع،
فتُضاف أي منصة بلا تعديل كود. لا يمسّ هذا الملف مصادقة provider.py.

EN: Data-driven provider registry + automatic platform detection from an API key
(prefix match, then probing /models). Extensible via config/providers.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, List, Optional, Tuple

_ROOT = Path(__file__).resolve().parent.parent
_USER_REGISTRY = _ROOT / "config" / "providers.json"

# سجل افتراضي — كل مدخل: name, base_url, model, prefixes[], auth(bearer|x-api-key)
# قابل للتوسيع/التجاوز عبر config/providers.json (لا تخصيص في المنطق).
_DEFAULT: List[dict] = [
    {"name": "openai", "base_url": "https://api.openai.com/v1",
     "model": "gpt-4o", "prefixes": ["sk-proj-"], "auth": "bearer"},
    {"name": "anthropic", "base_url": "https://api.anthropic.com/v1",
     "model": "claude-opus-4-8", "prefixes": ["sk-ant-"], "auth": "x-api-key"},
    {"name": "groq", "base_url": "https://api.groq.com/openai/v1",
     "model": "llama-3.3-70b-versatile", "prefixes": ["gsk_"], "auth": "bearer"},
    {"name": "openrouter", "base_url": "https://openrouter.ai/api/v1",
     "model": "anthropic/claude-sonnet-4-6", "prefixes": ["sk-or-"], "auth": "bearer"},
    {"name": "nvidia", "base_url": "https://integrate.api.nvidia.com/v1",
     "model": "meta/llama-3.1-70b-instruct", "prefixes": ["nvapi-"], "auth": "bearer"},
    {"name": "xai", "base_url": "https://api.x.ai/v1",
     "model": "grok-2-latest", "prefixes": ["xai-"], "auth": "bearer"},
    {"name": "perplexity", "base_url": "https://api.perplexity.ai",
     "model": "sonar", "prefixes": ["pplx-"], "auth": "bearer"},
    {"name": "fireworks", "base_url": "https://api.fireworks.ai/inference/v1",
     "model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
     "prefixes": ["fw_"], "auth": "bearer"},
    {"name": "cerebras", "base_url": "https://api.cerebras.ai/v1",
     "model": "llama3.1-70b", "prefixes": ["csk-"], "auth": "bearer"},
    {"name": "google", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
     "model": "gemini-2.0-flash", "prefixes": ["AIza"], "auth": "bearer"},
    {"name": "deepseek", "base_url": "https://api.deepseek.com/v1",
     "model": "deepseek-chat", "prefixes": [], "auth": "bearer"},
    {"name": "together", "base_url": "https://api.together.xyz/v1",
     "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo", "prefixes": [], "auth": "bearer"},
    {"name": "mistral", "base_url": "https://api.mistral.ai/v1",
     "model": "mistral-large-latest", "prefixes": [], "auth": "bearer"},
    {"name": "aerolink", "base_url": "https://capi.aerolink.lat/v1",
     "model": "claude-fable-5", "prefixes": [], "auth": "bearer"},
    {"name": "ollama", "base_url": "http://localhost:11434/v1",
     "model": "llama3.2", "prefixes": [], "auth": "bearer"},
]


def load_registry() -> List[dict]:
    """السجل الفعّال: الافتراضي مدموجاً مع config/providers.json (يُحدِّث/يضيف)."""
    reg = {p["name"]: dict(p) for p in _DEFAULT}
    if _USER_REGISTRY.exists():
        try:
            data = json.loads(_USER_REGISTRY.read_text(encoding="utf-8"))
            for p in data.get("providers", data if isinstance(data, list) else []):
                if isinstance(p, dict) and p.get("name") and p.get("base_url"):
                    reg[p["name"]] = {**reg.get(p["name"], {}),
                                      "prefixes": [], "auth": "bearer", "model": "", **p}
        except Exception:
            pass
    return list(reg.values())


def add_provider(name: str, base_url: str, model: str = "",
                 prefixes: Optional[List[str]] = None, auth: str = "bearer") -> bool:
    """يضيف/يحدّث مزوّداً في config/providers.json (توسيع لأي منصة بلا كود)."""
    name = (name or "").strip()
    base_url = (base_url or "").strip().rstrip("/")
    if not name or not base_url:
        return False
    existing = {}
    if _USER_REGISTRY.exists():
        try:
            existing = json.loads(_USER_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    providers = existing.get("providers", []) if isinstance(existing, dict) else []
    providers = [p for p in providers if p.get("name") != name]
    providers.append({"name": name, "base_url": base_url, "model": model or "",
                      "prefixes": prefixes or [], "auth": auth})
    _USER_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    _USER_REGISTRY.write_text(json.dumps({"providers": providers},
                                         ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def provider_names() -> List[str]:
    return [p["name"] for p in load_registry()]


def get_provider(name: str) -> Optional[dict]:
    name = (name or "").strip().lower()
    for p in load_registry():
        if p["name"].lower() == name:
            return p
    return None


def detect_by_prefix(key: str) -> Optional[dict]:
    """يطابق بادئة المفتاح مع السجل → مدخل المزوّد أو None."""
    key = (key or "").strip()
    if not key:
        return None
    for p in load_registry():
        for pref in p.get("prefixes", []):
            if pref and key.startswith(pref):
                return p
    return None


def headers_for(entry: dict, key: str) -> dict:
    """ترويسات المصادقة حسب نوع المزوّد (Bearer أو x-api-key)."""
    if entry.get("auth") == "x-api-key":
        return {"x-api-key": key, "anthropic-version": "2023-06-01",
                "Content-Type": "application/json", "User-Agent": "WeaverCode"}
    return {"Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "User-Agent": "WeaverCode"}


def models_urls(base_url: str) -> List[str]:
    """نقاط /models المرشّحة لرابط مزوّد."""
    base = base_url.rstrip("/")
    root = base[:-3].rstrip("/") if base.lower().endswith("/v1") else base
    urls, seen = [], set()
    for u in (root + "/v1/models", root + "/models", base + "/models"):
        if u not in seen:
            seen.add(u)
            urls.append(u)
    return urls


def _models_from_response(data) -> list:
    items = (data.get("data", data.get("models")) if isinstance(data, dict) else data)
    if not isinstance(items, list):
        return []
    out = []
    for m in items:
        mid = ((m.get("id") or m.get("name")) if isinstance(m, dict)
               else (m if isinstance(m, str) else None))
        if mid:
            out.append(str(mid))
    return out


HttpGet = Callable[[str, dict, int], Tuple[object, Optional[str]]]


def resolve_platform(key: str, http_get: HttpGet, current_base: str = "",
                     timeout: int = 8) -> Optional[dict]:
    """يحدّد منصة المفتاح: بادئة أولاً، ثم سبر نقاط /models للسجل.

    http_get(url, headers, timeout) -> (data|None, error|None).
    يُرجع مدخل المزوّد المطابق (مع 'models' مضافة) أو None. لا يبدّل شيئاً إن كان
    الرابط الحالي يعمل بالمفتاح أصلاً (فلا يُكسَر إعداد قائم مثل aerolink).
    """
    key = (key or "").strip()
    if not key:
        return None
    registry = load_registry()

    def _try(entry) -> Optional[dict]:
        headers = headers_for(entry, key)
        for url in models_urls(entry["base_url"]):
            data, err = http_get(url, headers, timeout)
            if not err:
                models = _models_from_response(data)
                if models:
                    e = dict(entry)
                    e["models"] = sorted(set(models))
                    e["source"] = url
                    return e
        return None

    # 1) كشف بالبادئة (سريع، بلا تسريب) ثم تأكيد بالنماذج
    pref = detect_by_prefix(key)
    if pref:
        got = _try(pref)
        if got:
            return got

    # 2) إن كان الرابط الحالي يعمل بالمفتاح → أبقِه (لا تبديل غير ضروري)
    cur = current_base.strip().rstrip("/")
    if cur:
        cur_entry = next((p for p in registry if p["base_url"].rstrip("/") == cur), None)
        cur_entry = cur_entry or {"name": "الحالي", "base_url": cur,
                                  "model": "", "auth": "bearer"}
        got = _try(cur_entry)
        if got:
            return None  # الرابط الحالي صالح، لا حاجة للتبديل

    # 3) سبر بقية مزوّدي السجل (يغطّي المفاتيح العامة بلا بادئة)
    for entry in registry:
        if pref and entry["name"] == pref["name"]:
            continue
        got = _try(entry)
        if got:
            return got
    return None
