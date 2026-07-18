"""
mentions.py — توسيع إشارات الملفات @file في رسائل المستخدم لـ WeaverCode
========================================================================

يسمح للمستخدم بالإشارة إلى ملف داخل رسالته بكتابة `@path/to/file`،
فيُحقن محتوى الملف تلقائياً في السياق قبل إرساله للنموذج — تماماً كما في
Claude Code.

أمثلة:
    "راجع @core/engine/provider.py وأخبرني عن الأخطاء"
    "قارن @a.py مع @b.py"

القواعد:
    - يُتعرَّف على @ فقط في بداية كلمة (مسبوقة بمسافة أو بداية السطر).
    - المسار ينتهي عند أول مسافة أو محرف غير صالح للمسارات.
    - عناوين البريد (user@host) تُتجاهل لأنها مسبوقة بحرف.
    - إشارة لملف غير موجود تبقى كما هي (لا تُوسَّع).
    - حد أقصى لحجم المحتوى المحقون لتفادي إغراق السياق.

EN: Expands `@file` mentions in a user prompt by inlining referenced file
contents as context blocks, mirroring Claude Code's @-mention behaviour.
Non-existent paths and email-like tokens are left untouched.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple

# حد أقصى لعدد الأحرف المحقونة لكل ملف (تفادي إغراق السياق)
_MAX_FILE_CHARS = 20_000
# حد أقصى لعدد الملفات المحقونة في رسالة واحدة
_MAX_FILES = 10

# @ في بداية كلمة، يتبعه مسار (حروف/أرقام/. _ - / ~)
_MENTION_RE = re.compile(r"(?:(?<=\s)|^)@([\w./~\-]+)")


def find_mentions(text: str) -> List[str]:
    """يستخرج كل مسارات @file المذكورة في النص (بالترتيب، بلا تكرار)."""
    seen: set = set()
    out: List[str] = []
    for m in _MENTION_RE.finditer(text):
        raw = m.group(1)
        # نتجاهل ما يشبه القرار المزدوج مثل @@ أو ينتهي بنقطة جملة
        path = raw.rstrip(".,;:!؟)")
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out


def _resolve(path_str: str, base_dir: Optional[Path]) -> Optional[Path]:
    """يحلّل مسار @mention إلى Path موجود فعلاً، وإلا None."""
    try:
        p = Path(path_str).expanduser()
        if not p.is_absolute() and base_dir is not None:
            candidate = (base_dir / p)
            if candidate.exists():
                p = candidate
        if p.exists() and p.is_file():
            return p
    except (OSError, ValueError):
        return None
    return None


def expand_mentions(text: str,
                    base_dir: Optional[Path] = None) -> Tuple[str, List[str]]:
    """
    يوسّع كل إشارات @file القابلة للحلّ في النص.

    Returns:
        (النص المُوسَّع, قائمة الملفات التي حُقنت فعلاً)

    النص الأصلي يبقى كما هو، وتُضاف كتل المحتوى في نهايته تحت عنوان
    "## الملفات المُشار إليها" حتى لا يُشوَّه سؤال المستخدم.
    """
    if "@" not in text:
        return text, []

    mentions = find_mentions(text)
    if not mentions:
        return text, []

    base = base_dir or Path.cwd()
    blocks: List[str] = []
    injected: List[str] = []

    for path_str in mentions:
        if len(injected) >= _MAX_FILES:
            break
        resolved = _resolve(path_str, base)
        if resolved is None:
            continue
        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        truncated = ""
        if len(content) > _MAX_FILE_CHARS:
            content = content[:_MAX_FILE_CHARS]
            truncated = "\n… (اقتُطع المحتوى)"
        lang = resolved.suffix.lstrip(".") or ""
        blocks.append(
            f"### `{path_str}`\n```{lang}\n{content}{truncated}\n```"
        )
        injected.append(path_str)

    if not blocks:
        return text, []

    appendix = "\n\n## الملفات المُشار إليها (@)\n" + "\n\n".join(blocks)
    return text + appendix, injected
