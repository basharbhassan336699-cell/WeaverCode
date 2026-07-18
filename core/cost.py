"""
cost.py — تتبّع التوكنات والتكلفة بالدولار لـ WeaverCode
========================================================

يقرأ حقل `usage` الحقيقي العائد من المزوّد بعد كل استدعاء ويجمع:
  - توكنات الإدخال (prompt/input)
  - توكنات الإخراج (completion/output)
  - التكلفة بالدولار حسب جدول أسعار لكل نموذج

⚠️ لا يمسّ هذا الملف طبقة المصادقة/المفاتيح في provider.py. هو قارئ فقط
   لبيانات الاستخدام التي يُرجعها المزوّد أصلاً.

الأسعار (دولار لكل مليون توكن) قابلة للتجاوز عبر البيئة:
    WEAVER_PRICE_INPUT   سعر مليون توكن إدخال
    WEAVER_PRICE_OUTPUT  سعر مليون توكن إخراج

EN: Reads the real `usage` field the provider already returns and accumulates
input/output tokens plus a USD cost from a per-model price table. Read-only —
never touches provider auth/keys.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


# ── جدول الأسعار: (سعر الإدخال, سعر الإخراج) لكل مليون توكن بالدولار ──────────
# أسعار تقريبية عامة؛ المطابقة بالبحث عن جزء من اسم النموذج (lowercase).
_PRICE_TABLE: Dict[str, Tuple[float, float]] = {
    # Anthropic Claude
    "claude-opus-4":     (15.0, 75.0),
    "claude-sonnet-4":   (3.0, 15.0),
    "claude-fable":      (3.0, 15.0),
    "claude-haiku-4":    (1.0, 5.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku":  (0.80, 4.0),
    "claude-3-opus":     (15.0, 75.0),
    "claude-3-haiku":    (0.25, 1.25),
    # OpenAI GPT
    "gpt-4o-mini":       (0.15, 0.60),
    "gpt-4o":            (2.50, 10.0),
    "gpt-4-turbo":       (10.0, 30.0),
    "gpt-4":             (30.0, 60.0),
    "gpt-3.5":           (0.50, 1.50),
    "o1-mini":           (3.0, 12.0),
    "o1":                (15.0, 60.0),
    # DeepSeek
    "deepseek-chat":     (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
    "deepseek":          (0.27, 1.10),
    # Groq / Llama (سريعة ورخيصة)
    "llama-3.3-70b":     (0.59, 0.79),
    "llama-3.1-8b":      (0.05, 0.08),
    "llama-3":           (0.59, 0.79),
    "mixtral":           (0.24, 0.24),
    "gemma":             (0.20, 0.20),
    # Qwen / others
    "qwen":              (0.40, 1.20),
}

# نماذج محلية مجانية (Ollama) — تكلفة صفر
_FREE_HINTS = ("ollama", "localhost", "local")


def resolve_price(model: str) -> Tuple[float, float]:
    """
    يُرجع (سعر الإدخال, سعر الإخراج) لكل مليون توكن للنموذج المعطى.
    الأولوية: متغيرات البيئة > جدول الأسعار > (0, 0) للمجهول/المحلي.
    """
    # تجاوز صريح عبر البيئة
    env_in = os.environ.get("WEAVER_PRICE_INPUT")
    env_out = os.environ.get("WEAVER_PRICE_OUTPUT")
    if env_in is not None and env_out is not None:
        try:
            return float(env_in), float(env_out)
        except ValueError:
            pass

    m = (model or "").lower()
    # نماذج محلية مجانية
    if any(h in m for h in _FREE_HINTS):
        return 0.0, 0.0
    # مطابقة بالاحتواء — أطول مفتاح مطابق أولاً (أدق)
    best: Optional[Tuple[float, float]] = None
    best_len = -1
    for key, price in _PRICE_TABLE.items():
        if key in m and len(key) > best_len:
            best = price
            best_len = len(key)
    return best if best is not None else (0.0, 0.0)


@dataclass
class TokenUsage:
    """إجمالي التوكنات والتكلفة المتراكمة."""
    input_tokens:  int = 0
    output_tokens: int = 0
    requests:      int = 0
    cost_usd:      float = 0.0
    pricing_known: bool = True   # False إن لم نعرف سعر أي نموذج مُستخدم

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _extract_tokens(usage: Dict[str, Any]) -> Tuple[int, int]:
    """
    يستخرج (إدخال, إخراج) من حقل usage بأي صيغة:
      OpenAI:    prompt_tokens / completion_tokens
      Anthropic: input_tokens / output_tokens
    """
    if not isinstance(usage, dict):
        return 0, 0
    inp = (usage.get("prompt_tokens")
           or usage.get("input_tokens") or 0)
    out = (usage.get("completion_tokens")
           or usage.get("output_tokens") or 0)
    try:
        return int(inp or 0), int(out or 0)
    except (ValueError, TypeError):
        return 0, 0


class CostTracker:
    """يجمع الاستخدام والتكلفة عبر استدعاءات المزوّد المتعددة."""

    def __init__(self):
        self.usage = TokenUsage()

    def record(self, response: Dict[str, Any],
               model: Optional[str] = None) -> Tuple[int, int, float]:
        """
        يسجّل استخدام استدعاء واحد من رد المزوّد.

        Returns: (توكنات الإدخال, توكنات الإخراج, تكلفة هذا الاستدعاء بالدولار).
        """
        if not isinstance(response, dict):
            return 0, 0, 0.0
        inp, out = _extract_tokens(response.get("usage", {}))
        used_model = model or response.get("model") or ""
        pin, pout = resolve_price(used_model)
        call_cost = (inp / 1_000_000.0) * pin + (out / 1_000_000.0) * pout

        self.usage.input_tokens += inp
        self.usage.output_tokens += out
        self.usage.requests += 1
        self.usage.cost_usd += call_cost
        if (inp or out) and pin == 0.0 and pout == 0.0 \
                and not any(h in used_model.lower() for h in _FREE_HINTS):
            # استُخدمت توكنات لكن لا نعرف السعر → علّم أن التقدير غير مكتمل
            self.usage.pricing_known = False
        return inp, out, call_cost

    def reset(self) -> None:
        self.usage = TokenUsage()

    def summary(self) -> str:
        """ملخص نصّي مُنسّق للعرض (لأمر /cost)."""
        u = self.usage
        lines = [
            "💰 التكلفة والاستخدام:",
            f"  الطلبات:        {u.requests}",
            f"  توكنات الإدخال:  {u.input_tokens:,}",
            f"  توكنات الإخراج:  {u.output_tokens:,}",
            f"  الإجمالي:        {u.total_tokens:,} توكن",
        ]
        if u.pricing_known:
            lines.append(f"  التكلفة:        ${u.cost_usd:.4f}")
        else:
            lines.append(f"  التكلفة:        ${u.cost_usd:.4f} "
                         "(تقديرية — بعض النماذج بلا سعر معروف)")
        return "\n".join(lines)


# ── تقدير عدد التوكنات لنص (حين لا يوفّر المزوّد usage) ───────────────────────

def estimate_tokens(text: str) -> int:
    """
    تقدير تقريبي لعدد التوكنات: ~4 أحرف/توكن للإنجليزية، والعربية أكثف
    قليلاً. تقدير كافٍ لعرض حجم السياق حين لا يُرجع المزوّد usage دقيقاً.
    """
    if not text:
        return 0
    # متوسط عملي: 3.5 حرف لكل توكن (يراعي خليط عربي/إنجليزي/رموز)
    return max(1, int(len(text) / 3.5))
