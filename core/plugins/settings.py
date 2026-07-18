"""
settings.py — محلّل ملفات إعدادات الـ Plugins لـ WeaverCode
============================================================

يقرأ ملفات إعدادات على هيئة Markdown مع YAML frontmatter، عادةً بالمسار:

    .claude/<plugin-name>.local.md

بنية الملف:

    ---
    enabled: true
    max_value: 42
    label: "value with spaces"
    tags: ["a", "b", "c"]
    ---

    # نص حر (body)
    محتوى إضافي يُستعمل كسياق أو توثيق.

يفصل هذا المحلّل الـ frontmatter (قيم مُعرَّبة إلى أنواع بايثون) عن الـ body.

EN: Parses plugin settings files (`.claude/<plugin>.local.md`) that use
Markdown with a YAML-style frontmatter block. Returns typed values without
requiring PyYAML — a small, dependency-free parser tuned for the field kinds
documented in the reference (string/quoted/bool/int/float/list).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ── تحويل قيمة نصّية واحدة إلى نوع بايثون ────────────────────────────────────

def _coerce_scalar(raw: str) -> Any:
    """يحوّل قيمة frontmatter نصّية إلى bool/int/float/str حسب شكلها."""
    v = raw.strip()
    if not v:
        return ""
    # نص بين علامتي اقتباس → إزالة الاقتباس والإبقاء على النص كما هو
    if (len(v) >= 2) and ((v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")):
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "none", "~"):
        return None
    # عدد صحيح
    if re.fullmatch(r"[+-]?\d+", v):
        try:
            return int(v)
        except ValueError:
            return v
    # عدد عشري
    if re.fullmatch(r"[+-]?\d*\.\d+", v):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def _parse_inline_list(raw: str) -> List[Any]:
    """يحلّل قائمة مضمّنة: ["a", "b", 3]  →  ['a', 'b', 3]."""
    inner = raw.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    if not inner.strip():
        return []
    items: List[Any] = []
    # تقسيم على الفواصل مع احترام الاقتباس البسيط
    for part in _split_top_level_commas(inner):
        part = part.strip()
        if part:
            items.append(_coerce_scalar(part))
    return items


def _split_top_level_commas(s: str) -> List[str]:
    """يقسّم على الفواصل خارج علامات الاقتباس."""
    out: List[str] = []
    buf = []
    quote = ""
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in ('"', "'"):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


# ── فصل الـ frontmatter عن الـ body ─────────────────────────────────────────

def split_frontmatter(text: str) -> Tuple[str, str]:
    """
    يفصل كتلة frontmatter (بين سطرين ---) عن باقي المحتوى.
    يُرجع (frontmatter_text, body_text). إن لم توجد كتلة → ("", text).
    """
    # يجب أن يبدأ الملف بـ --- (مع تجاهل مسافات/أسطر بادئة)
    m = re.match(r"^\s*---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)$",
                 text, re.DOTALL)
    if not m:
        return "", text
    return m.group(1), m.group(2)


def parse_frontmatter(fm_text: str) -> Dict[str, Any]:
    """
    يحلّل نص frontmatter إلى قاموس بأنواع بايثون.
    يدعم: string, quoted string, bool, int, float, inline list.
    يتجاهل الأسطر الفارغة والتعليقات (#).
    """
    result: Dict[str, Any] = {}
    for line in fm_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        # إزالة تعليق سطري بعد القيمة (عندما لا تكون داخل اقتباس)
        if value.lstrip().startswith("[") and value.rstrip().endswith("]"):
            result[key] = _parse_inline_list(value)
        else:
            result[key] = _coerce_scalar(value)
    return result


def parse_settings_text(text: str) -> Dict[str, Any]:
    """يحلّل نص إعدادات كامل → {"settings": {...}, "body": "..."}."""
    fm, body = split_frontmatter(text)
    return {
        "settings": parse_frontmatter(fm) if fm else {},
        "body": body.strip(),
    }


def parse_settings_file(path: Path) -> Dict[str, Any]:
    """يقرأ ويحلّل ملف إعدادات من القرص. يُرجع {} إن لم يوجد."""
    p = Path(path)
    if not p.exists():
        return {"settings": {}, "body": ""}
    try:
        return parse_settings_text(p.read_text(encoding="utf-8"))
    except Exception:
        return {"settings": {}, "body": ""}


def load_plugin_settings(plugin_name: str,
                         project_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    يحمّل إعدادات plugin من `.claude/<plugin_name>.local.md`.
    يبحث في جذر المشروع ثم في مجلد المستخدم (~/.claude).

    يُرجع قاموس القيم فقط (settings)، فارغ إن لم يوجد ملف.
    """
    candidates: List[Path] = []
    if project_root:
        candidates.append(Path(project_root) / ".claude" / f"{plugin_name}.local.md")
    candidates.append(Path.cwd() / ".claude" / f"{plugin_name}.local.md")
    candidates.append(Path.home() / ".claude" / f"{plugin_name}.local.md")
    for c in candidates:
        if c.exists():
            return parse_settings_file(c).get("settings", {})
    return {}
