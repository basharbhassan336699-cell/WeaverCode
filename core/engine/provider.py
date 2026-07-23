"""
provider.py — محرك الاتصال بمزودي النماذج
================================================

يدعم أي مزود ذكاء اصطناعي عبر صيغتين تلقائياً:

1. صيغة Anthropic  (POST /v1/messages)
   تُفعَّل تلقائياً عند اكتشاف "aerolink" أو "anthropic" في عنوان الـ URL.

2. صيغة OpenAI     (POST /chat/completions)
   تُستخدم لبقية المزودين: OpenRouter, Groq, DeepSeek, OpenAI, Ollama...

يستخدم `curl` داخلياً بدل httpx لتجاوز مشاكل إعادة التوجيه (redirect) والحالة 305،
ويدعم `follow_redirects` و`proxy` اختيارياً، مع معالجة كاملة للأخطاء برسائل عربية واضحة.

مهما كانت الصيغة، يُعيد `complete()` قاموساً بشكل OpenAI (choices[0].message)
حتى يبقى بقية المشروع (query_engine) موحّداً دون تغيير.
"""

import os
import re
import json
import shutil
import asyncio
from typing import AsyncGenerator, Optional, Dict, Any, List
from dataclasses import dataclass, field


# ── نموذج الرسالة الموحّد ────────────────────────────────────────────────────

@dataclass
class Message:
    role: str  # user | assistant | system | tool
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    # مسارات وسائط (صور/PDF) تُرفَق مع رسالة user لتُرسل للنموذج كـ vision blocks.
    # حقل إضافي غير كاسر — لا يؤثر على المصادقة/المفاتيح، فقط على تركيب الرسالة.
    media: Optional[List[str]] = None


# ── بناء كتل الوسائط (رؤية) — يعتمد core.multimodal، لا يمسّ المصادقة ──────────

# ── استخراج استدعاءات الأدوات المكتوبة كنصّ (<invoke name="...">) ─────────────
# بعض النماذج/البوابات تُخرج استدعاء الأداة كنصّ بصيغة (antml/DSML) بدل كتلة
# tool_use الأصلية، فتظهر كنصّ ميت ولا تُنفَّذ. نستخرجها هنا لتُنفَّذ فعلياً.
_PARAM_ALIAS = {
    "filepath": "path", "file_path": "path", "filename": "path", "file": "path",
    "dir": "path", "directory": "path", "cmd": "command", "bash": "command",
    "text": "content", "body": "content", "data": "content",
}


def _clean_param_value(v: str) -> str:
    v = (v or "").strip()
    # نزع بادئة نوعية غريبة مثل: string="true">...
    m = re.match(r'^(?:string|str|text|number|int|bool|boolean)\s*=\s*"[^"]*"\s*>\s*',
                 v, re.IGNORECASE)
    if m:
        v = v[m.end():].strip()
    return v


def _extract_text_tool_calls(text: str) -> List[Dict[str, Any]]:
    """يستخرج استدعاءات أدوات مكتوبة كنصّ بصيغة <invoke name="X"><parameter…>.

    مبني على حدود الوسوم (لا يعتمد على إغلاق سليم) ليتحمّل التشويه. يُرجع قائمة
    tool_calls بصيغة OpenAI الموحّدة، أو [] إن لم يجد.
    """
    if not text or "invoke" not in text.lower():
        return []
    calls: List[Dict[str, Any]] = []
    starts = [m.start() for m in re.finditer(
        r'<\s*(?:antml:)?invoke\s+name\s*=\s*"', text, re.IGNORECASE)]
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[s:end]
        nm = re.search(r'name\s*=\s*"([^"]+)"', block, re.IGNORECASE)
        if not nm:
            continue
        name = nm.group(1).strip()
        args: Dict[str, Any] = {}
        pstarts = [m.start() for m in re.finditer(
            r'<\s*(?:antml:)?parameter\b', block, re.IGNORECASE)]
        for j, ps in enumerate(pstarts):
            pend = pstarts[j + 1] if j + 1 < len(pstarts) else len(block)
            pblock = block[ps:pend]
            # اسم الوسيط في أي مكان داخل وسم الفتح (يتحمّل خصائص إضافية مثل
            # string="true" التي تُخرجها بعض النماذج/البوابات)
            pm = re.search(r'name\s*=\s*"([^"]+)"', pblock, re.IGNORECASE)
            if not pm:
                continue
            k = pm.group(1).strip()
            k = _PARAM_ALIAS.get(k.lower(), k)
            # القيمة تبدأ بعد نهاية وسم الفتح (أول '>' بعد الاسم)
            gt = pblock.find(">", pm.end())
            v = pblock[gt + 1:] if gt != -1 else pblock[pm.end():]
            v = re.split(r'<\s*/?\s*(?:antml:)?(?:parameter|invoke)',
                         v, 1, flags=re.IGNORECASE)[0]
            if k:
                args[k] = _clean_param_value(v)
        if name:
            calls.append({
                "id": f"txt_{i}", "type": "function",
                "function": {"name": name,
                             "arguments": json.dumps(args, ensure_ascii=False)},
            })
    return calls


def _apply_text_tool_calls(content: str):
    """يفصل النصّ عن استدعاءات الأدوات النصّية. يُرجع (النص_قبل_الاستدعاءات, tool_calls)."""
    calls = _extract_text_tool_calls(content)
    if not calls:
        return content, None
    cut = re.search(r'<\s*(?:antml:)?invoke|<\s*\|?\s*DSML', content or "",
                    re.IGNORECASE)
    head = (content[:cut.start()].strip() if cut else "")
    # تنظيف وسوم تفكير نصية دخيلة (<think/> …) من النص المعروض
    head = re.sub(r'<\s*/?\s*think\s*/?\s*>', '', head, flags=re.IGNORECASE).strip()
    return head, calls


def _prompt_cache_enabled() -> bool:
    """هل نُفعّل تخزين الأدوات/النظام بالكاش (Anthropic prompt caching)؟

    مُفعّل افتراضياً — يجعل الأدوات وبروموه النظام تُرسَل مرة وتُقرأ من الكاش
    (أرخص/أسرع) بدل إعادة معالجتها كل طلب، تماماً كـ Claude Code. للتعطيل الفوري
    عند أي مشكلة مع بوابة لا تدعمه: WEAVER_PROMPT_CACHE=0.
    """
    return os.environ.get("WEAVER_PROMPT_CACHE", "1").strip().lower() not in (
        "0", "false", "no", "off")


def _media_blocks_anthropic(paths: List[str]) -> List[Dict[str, Any]]:
    """كتل صورة/مستند بصيغة Anthropic لمسارات وسائط موجودة (يتجاهل الفاشل)."""
    out: List[Dict[str, Any]] = []
    try:
        from core.multimodal import build_anthropic_block, is_multimodal
    except Exception:
        return out
    for p in paths or []:
        try:
            if is_multimodal(p):
                out.append(build_anthropic_block(p))
        except Exception:
            continue
    return out


def _media_blocks_openai(paths: List[str]) -> List[Dict[str, Any]]:
    """كتل صورة بصيغة OpenAI لمسارات وسائط موجودة (يتجاهل الفاشل)."""
    out: List[Dict[str, Any]] = []
    try:
        from core.multimodal import build_openai_block, is_image
    except Exception:
        return out
    for p in paths or []:
        try:
            # OpenAI vision يدعم الصور؛ نتخطّى PDF هنا لتفادي رفض الصيغة.
            if is_image(p):
                out.append(build_openai_block(p))
        except Exception:
            continue
    return out


# ── إعدادات المزود ───────────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    api_key: str
    base_url: str
    model: str
    max_tokens: int = 8192
    temperature: float = 0.7
    proxy: Optional[str] = None
    follow_redirects: bool = True
    timeout: int = 180
    retries: int = 2
    retry_base: float = 1.0
    extra_headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        """تحميل الإعدادات من متغيرات البيئة"""
        def _bool(name: str, default: bool) -> bool:
            v = os.environ.get(name)
            if v is None:
                return default
            return v.strip().lower() in ("1", "true", "yes", "on", "نعم")

        return cls(
            api_key=os.environ.get("WEAVER_API_KEY", ""),
            base_url=os.environ.get("WEAVER_BASE_URL", "https://openrouter.ai/api/v1").strip(),
            model=os.environ.get("WEAVER_MODEL", "anthropic/claude-sonnet-4-6").strip(),
            max_tokens=int(os.environ.get("WEAVER_MAX_TOKENS", "8192")),
            temperature=float(os.environ.get("WEAVER_TEMPERATURE", "0.7")),
            # يقبل WEAVER_PROXY أو متغيرات البيئة القياسية HTTPS_PROXY / HTTP_PROXY
            proxy=(os.environ.get("WEAVER_PROXY")
                   or os.environ.get("HTTPS_PROXY")
                   or os.environ.get("HTTP_PROXY")
                   or None),
            follow_redirects=_bool("WEAVER_FOLLOW_REDIRECTS", True),
            timeout=int(os.environ.get("WEAVER_TIMEOUT", "180")),
            retries=int(os.environ.get("WEAVER_RETRIES", "2")),
            retry_base=float(os.environ.get("WEAVER_RETRY_BASE", "1.0")),
        )


class ProviderError(RuntimeError):
    """خطأ اتصال أو استجابة من المزود — رسالته عربية واضحة"""


class TransientProviderError(ProviderError):
    """خطأ عابر (شبكة/DNS/مهلة/429/5xx) — يستحق إعادة المحاولة."""


class RequestTooLargeError(ProviderError):
    """
    الطلب أكبر من حدّ المزوّد (HTTP 413 أو حدّ التوكِنات/الدقيقة TPM).
    قابل للإصلاح تلقائياً بتقليل max_tokens وإعادة المحاولة.
    """
    def __init__(self, msg: str, limit: int = 0, requested: int = 0):
        super().__init__(msg)
        self.limit = limit
        self.requested = requested


# أكواد خروج curl العابرة: 6 resolve, 7 connect, 28 timeout, 35 ssl, 52 empty, 56 recv
_CURL_TRANSIENT_CODES = {6, 7, 28, 35, 52, 55, 56}
# حالات HTTP العابرة (تُعاد المحاولة)؛ ما عداها (401/403/404/رصيد) دائم
_HTTP_TRANSIENT = {408, 425, 429, 500, 502, 503, 504}


class WeaverProvider:
    """
    موصل عالمي لأي مزود نماذج ذكاء اصطناعي.
    يكتشف صيغة البروتوكول تلقائياً (Anthropic أو OpenAI) وينفّذ عبر curl.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig.from_env()
        # آخر استجابة خام من المزوّد (لأغراض التشخيص عند رجوع نصّ فارغ)
        self.last_raw: str = ""
        # تجاوز الصيغة المكتشَف تلقائياً بعد نجاح الصيغة الأخرى (تعلّم ذاتي للجلسة)
        # None = استخدم الاكتشاف العادي؛ True = Anthropic؛ False = OpenAI
        self._format_override: Optional[bool] = None
        # بعد نجاح إرسال بلا أدوات على بوابة ترفض الأدوات (305)، نتذكّره للجلسة
        self._drop_tools: bool = False
        # قاطع دائرة: بعد نجاح «الوضع الأدنى» على بوابة مقيّدة، نرسل به مباشرةً
        # (طلب واحد) بدل سلّم المرشّحين — حتى لا نستنزف توكينات المستخدم.
        self._bare_mode: bool = False
        # نحمّل ما تعلّمناه سابقاً عن هذا المزوّد (يُوفّر إعادة الاكتشاف عبر التشغيلات)
        self._load_quirk_cache()
        if not shutil.which("curl"):
            raise ProviderError(
                "❌ الأداة curl غير مثبّتة على النظام. "
                "ثبّتها أولاً:  sudo apt install curl  (أو pkg install curl على Termux)"
            )

    # ── ذاكرة تكيّف المزوّد (تُوفّر إعادة الاكتشاف واستنزاف التوكينات) ─────────

    @staticmethod
    def _quirk_cache_path():
        """مسار ملف ذاكرة تكيّف المزوّد. يحترم WEAVER_PROVIDER_CACHE:
        قيمة off/0/none/'' → تعطيل تام (يُرجع None)؛ مسار → يُستخدم كما هو."""
        from pathlib import Path
        override = os.environ.get("WEAVER_PROVIDER_CACHE")
        if override is not None:
            if override.strip().lower() in ("off", "0", "none", "no", "false", ""):
                return None
            return Path(os.path.expanduser(override))
        return Path(os.path.expanduser("~/.weaver/provider_cache.json"))

    def _load_quirk_cache(self) -> None:
        """تحميل ما تعلّمناه سابقاً عن هذا المزوّد (bare/صيغة/إسقاط أدوات)."""
        try:
            path = self._quirk_cache_path()
            if path is None or not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            q = data.get(self.config.base_url.rstrip("/"))
            if not isinstance(q, dict):
                return
            if q.get("bare_mode"):
                self._bare_mode = True
            if isinstance(q.get("format_override"), bool):
                self._format_override = q["format_override"]
            if q.get("drop_tools"):
                self._drop_tools = True
            if isinstance(q.get("max_tokens"), int) and q["max_tokens"] > 0:
                self.config.max_tokens = min(self.config.max_tokens, q["max_tokens"])
        except Exception:
            pass  # الكاش مساعِد فقط — لا يُسقط النظام

    def _save_quirk_cache(self) -> None:
        """حفظ ما تعلّمناه لهذا المزوّد كي لا نُعيد اكتشافه في التشغيل القادم."""
        try:
            path = self._quirk_cache_path()
            if path is None:
                return
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    data = {}
            data[self.config.base_url.rstrip("/")] = {
                "bare_mode": self._bare_mode,
                "format_override": self._format_override,
                "drop_tools": self._drop_tools,
                "max_tokens": self.config.max_tokens,
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except Exception:
            pass

    # ── اكتشاف الصيغة ────────────────────────────────────────────────────────

    def _is_anthropic(self) -> bool:
        """
        هل يجب استخدام صيغة Anthropic (/v1/messages)؟
        تُفعَّل عند وجود aerolink أو anthropic في عنوان المزود،
        أو عند ضبط WEAVER_API_FORMAT=anthropic صراحةً.
        """
        forced = os.environ.get("WEAVER_API_FORMAT", "").strip().lower()
        if forced in ("anthropic", "messages"):
            return True
        if forced in ("openai", "chat"):
            return False
        # تجاوز مُتعلَّم في هذه الجلسة (بعد نجاح الصيغة الأخرى تلقائياً)
        if self._format_override is not None:
            return self._format_override
        url = self.config.base_url.lower()
        return "aerolink" in url or "anthropic" in url

    def _format_forced(self) -> bool:
        """هل ثبّت المستخدم الصيغة صراحةً عبر WEAVER_API_FORMAT؟"""
        return os.environ.get("WEAVER_API_FORMAT", "").strip().lower() in (
            "anthropic", "messages", "openai", "chat")

    @staticmethod
    def _response_is_empty(resp: Dict[str, Any]) -> bool:
        """هل الرد بلا نصّ وبلا استدعاءات أدوات (فارغ فعلاً)؟"""
        try:
            msg = resp["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return True
        has_text = bool((msg.get("content") or "").strip())
        has_tools = bool(msg.get("tool_calls"))
        return not (has_text or has_tools)

    async def _complete_format(
        self, messages: List[Message], tools: Optional[List[Dict]], anthropic: bool,
        bare: bool = False,
    ) -> Dict[str, Any]:
        """
        تنفيذ استدعاء واحد بصيغة محددة (Anthropic أو OpenAI)، مع إصلاح ذاتي
        لخطأ «الطلب أكبر من الحدّ» (413/TPM): يقلّل max_tokens ليلائم حدّ المزوّد
        ويعيد المحاولة (حتى 3 مرات)، ويتذكّر الحجم الأصغر لبقية الجلسة.

        bare=True: طلب أدنى يطابق ما ينجح يدوياً على البوابات المقيّدة —
        بلا system وبلا tools وبلا temperature وبـ max_tokens صغير.
        """
        attempts = 0
        while True:
            try:
                if anthropic:
                    payload = self._build_anthropic_payload(messages, tools,
                                                            stream=False, bare=bare)
                    data = await self._run_curl(self._anthropic_url(), payload)
                    return self._anthropic_to_openai_response(data)
                payload = self._build_openai_payload(messages, tools,
                                                     stream=False, bare=bare)
                return await self._run_curl(self._openai_url(), payload)
            except RequestTooLargeError as e:
                attempts += 1
                old = self.config.max_tokens
                if e.limit and e.requested and e.requested > e.limit:
                    # قلّل بمقدار الفائض فوق الحدّ + هامش أمان
                    new = old - (e.requested - e.limit) - 256
                else:
                    new = old // 2
                new = max(512, new)
                if new >= old or attempts > 3:
                    raise
                self.config.max_tokens = new  # يبقى مصغّراً لبقية الجلسة

    # ── بناء عناوين النقاط النهائية ───────────────────────────────────────────

    def _anthropic_url(self) -> str:
        b = self.config.base_url.rstrip("/")
        if b.endswith("/messages"):
            return b
        if b.endswith("/v1"):
            return b + "/messages"
        return b + "/v1/messages"

    def _openai_url(self) -> str:
        b = self.config.base_url.rstrip("/")
        if b.endswith("/chat/completions"):
            return b
        return b + "/chat/completions"

    # ── ترويسات الطلب ─────────────────────────────────────────────────────────

    def _headers(self) -> Dict[str, str]:
        if self._is_anthropic():
            headers = {
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01",
            }
            # Anthropic الرسمي يتطلب x-api-key؛ أما البوابات المتوافقة (aerolink…)
            # فتستخدم Bearer فقط. نطابق تماماً ما يعمل يدوياً حتى لا نُحفّز 305.
            if "api.anthropic.com" in self.config.base_url.lower():
                headers["x-api-key"] = self.config.api_key
            else:
                headers["Authorization"] = f"Bearer {self.config.api_key}"
        else:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            }
        headers.update(self.config.extra_headers)
        return headers

    # ── تحويل الرسائل/الأدوات إلى صيغة OpenAI ─────────────────────────────────

    def _msg_to_openai(self, msg: Message) -> Dict:
        d: Dict[str, Any] = {"role": msg.role, "content": msg.content}
        # وسائط (رؤية) على رسالة user → صيغة OpenAI multipart
        if msg.role == "user" and msg.media:
            blocks = _media_blocks_openai(msg.media)
            if blocks:
                parts: List[Dict[str, Any]] = []
                if msg.content:
                    parts.append({"type": "text", "text": msg.content})
                parts.extend(blocks)
                d["content"] = parts
        if msg.tool_calls:
            d["tool_calls"] = msg.tool_calls
        if msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        if msg.name:
            d["name"] = msg.name
        return d

    def _build_openai_payload(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        bare: bool = False,
    ) -> Dict[str, Any]:
        if bare:
            # طلب أدنى: بلا system/tools/temperature، max_tokens صغير
            conv = [self._msg_to_openai(m) for m in messages if m.role != "system"]
            return {
                "model": self.config.model,
                "messages": conv,
                "max_tokens": min(self.config.max_tokens, 1024),
                "stream": stream,
            }
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [self._msg_to_openai(m) for m in messages],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    # ── تحويل الرسائل/الأدوات إلى صيغة Anthropic ──────────────────────────────

    @staticmethod
    def _tools_to_anthropic(tools: List[Dict], cache: bool = False) -> List[Dict]:
        """تحويل مخطط أدوات OpenAI إلى مخطط Anthropic.

        عند cache=True نضع cache_control على آخر أداة → تُخزَّن كل الأدوات مرة
        واحدة وتُقرأ من الكاش في الطلبات التالية (مثل Claude Code). الأدوات تبقى
        تُرسَل في كل دورة (النموذج يحتاجها ليستدعيها) لكنها لا تُعاد معالجتها.
        """
        converted = []
        for t in tools:
            fn = t.get("function", t)
            converted.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        if cache and converted:
            converted[-1]["cache_control"] = {"type": "ephemeral"}
        return converted

    def _build_anthropic_payload(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
        bare: bool = False,
    ) -> Dict[str, Any]:
        if bare:
            # طلب أدنى يطابق ما ينجح يدوياً: بلا system/tools/temperature،
            # max_tokens صغير، رسائل user/assistant النصّية فقط.
            conv_min = [{"role": m.role, "content": m.content or ""}
                        for m in messages
                        if m.role in ("user", "assistant") and (m.content or "").strip()]
            if not conv_min:
                conv_min = [{"role": "user", "content": "مرحبا"}]
            return {
                "model": self.config.model,
                "max_tokens": min(self.config.max_tokens, 1024),
                "messages": conv_min,
            }
        system_parts: List[str] = []
        conv: List[Dict[str, Any]] = []

        for m in messages:
            if m.role == "system":
                if m.content:
                    system_parts.append(m.content)
                continue

            if m.role == "tool":
                # نتيجة أداة → رسالة user تحمل كتلة tool_result
                conv.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id or "",
                        "content": m.content or "",
                    }],
                })
                continue

            if m.role == "assistant" and m.tool_calls:
                blocks: List[Dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    fn = tc.get("function", {})
                    raw_args = fn.get("arguments", "{}")
                    try:
                        parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except (json.JSONDecodeError, TypeError):
                        parsed = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": parsed or {},
                    })
                conv.append({"role": "assistant", "content": blocks})
                continue

            # رسائل user/assistant النصية العادية — مع دعم الوسائط (رؤية)
            if m.role == "user" and m.media:
                blocks = _media_blocks_anthropic(m.media)
                if blocks:
                    parts: List[Dict[str, Any]] = list(blocks)
                    if m.content:
                        parts.append({"type": "text", "text": m.content})
                    conv.append({"role": "user", "content": parts})
                    continue
            conv.append({"role": m.role, "content": m.content or ""})

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": conv,
        }
        cache = _prompt_cache_enabled()
        if system_parts:
            system_text = "\n\n".join(system_parts)
            if cache:
                # نظام ككتلة واحدة مع cache_control → يُخزَّن ويُقرأ من الكاش
                payload["system"] = [{
                    "type": "text", "text": system_text,
                    "cache_control": {"type": "ephemeral"},
                }]
            else:
                payload["system"] = system_text
        if tools:
            payload["tools"] = self._tools_to_anthropic(tools, cache=cache)
        if stream:
            payload["stream"] = True
        return payload

    # ── تحويل رد Anthropic إلى شكل OpenAI الموحّد ─────────────────────────────

    @staticmethod
    def _anthropic_to_openai_response(data: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(data, dict):
            data = {}

        # ── حالة (أ): الوسيط أعاد شكل OpenAI أصلاً (شائع في بوابات "capi") ────
        # بعض الوسطاء المتوافقين (aerolink وغيره) يعيدون {choices:[{message}]}
        # حتى على /v1/messages. نمرّره كما هو حتى لا يضيع النص.
        if isinstance(data.get("choices"), list) and data["choices"]:
            ch0 = data["choices"][0] or {}
            msg = ch0.get("message") or ch0.get("delta") or {}
            if isinstance(msg, dict) and ("content" in msg or "tool_calls" in msg):
                out_content = msg.get("content") or ""
                out_tools = msg.get("tool_calls")
                # النموذج كتب الاستدعاءات كنصّ (<invoke…>) بدل tool_calls الأصلية →
                # استخرجها لتُنفَّذ فعلياً (سبب «يكتب الأدوات ككود ولا ينفّذها»).
                if not out_tools and isinstance(out_content, str):
                    head, extracted = _apply_text_tool_calls(out_content)
                    if extracted:
                        out_tools = extracted
                        out_content = head
                out_msg: Dict[str, Any] = {
                    "role": msg.get("role", "assistant"),
                    "content": out_content,
                }
                if out_tools:
                    out_msg["tool_calls"] = out_tools
                return {
                    "id": data.get("id", ""),
                    "model": data.get("model", ""),
                    "choices": [{
                        "index": 0,
                        "message": out_msg,
                        # عند وجود tool_calls (بما فيها المستخرَجة من نصّ) نُجبر
                        # finish_reason=tool_calls حتى تُنفّذها الحلقة (لا تتوقف).
                        "finish_reason": ("tool_calls" if out_msg.get("tool_calls")
                                          else (ch0.get("finish_reason") or "stop")),
                    }],
                    "usage": data.get("usage", {}),
                }

        text_parts: List[str] = []
        thinking_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        content = data.get("content")
        # ── حالة (ب): content كسلسلة نصية بدل مصفوفة كتل ─────────────────────
        if isinstance(content, str):
            text_parts.append(content)
            content = []
        elif content is None:
            content = []

        for block in content or []:
            if isinstance(block, str):
                text_parts.append(block)
                continue
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" or (btype is None and "text" in block):
                text_parts.append(block.get("text", ""))
            elif btype in ("thinking", "redacted_thinking"):
                # النماذج التفكيرية (مثل claude-fable-5) تُرجع كتلة تفكير قبل النص.
                # لا نعرضها كإجابة عادةً، لكن نحتفظ بها احتياطاً إن غاب نص الإجابة.
                t = block.get("thinking") or block.get("text") or ""
                if t:
                    thinking_parts.append(t)
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                })
            elif btype is None and "thinking" in block:
                t = block.get("thinking") or ""
                if t:
                    thinking_parts.append(t)

        # ── حالة (ج): احتياطي — بعض الوسطاء يضعون النص في completion/text ─────
        if not text_parts and not tool_calls:
            for k in ("completion", "text", "output_text"):
                v = data.get(k)
                if isinstance(v, str) and v.strip():
                    text_parts.append(v)
                    break

        # ── حالة (ج-2): استجابة تفكير فقط بلا نص (نموذج تفكيري اقتُطع أو لم يُخرج
        # كتلة نص) → نعرض محتوى التفكير كإجابة بدل ترك الرد فارغاً. برمجة حقيقية:
        # المستخدم يرى تحليل النموذج الفعلي (وصف الصورة/الملف) لا رسالة «لا نص».
        if not text_parts and not tool_calls and thinking_parts:
            text_parts.append("\n".join(thinking_parts))

        stop_reason = data.get("stop_reason", "end_turn")

        # ── حالة (د): رفض صريح من النموذج (stop_reason="refusal") ─────────────
        # النموذج قبل الاتصال (HTTP 200) لكنه رفض التوليد لسياسة الاستخدام.
        # نُظهر السبب بوضوح بدل تركه فارغاً حتى لا يظنّ المستخدم أن النظام معطّل.
        if not text_parts and not tool_calls and stop_reason == "refusal":
            details = data.get("stop_details") or {}
            category = details.get("category", "")
            explanation = details.get("explanation", "")
            text_parts.append(
                "⛔ رفض المزوّد تنفيذ هذا الطلب.\n"
                + (f"• الفئة: {category}\n" if category else "")
                + (f"• السبب: {explanation}\n" if explanation else "")
                + "\nإن تكرّر مع طلبات بسيطة، جرّب مفتاحاً آخر أو انتظر إعادة تعيين الرصيد."
            )

        # ── حالة (هـ): النموذج كتب الاستدعاءات كنصّ (<invoke…>) بدل tool_use ──
        # نستخرجها لتُنفَّذ فعلياً بدل عرضها كنصّ ميت (سبب «يكتب الأدوات ولا ينفّذ»).
        content_text = "".join(text_parts) if text_parts else ""
        if not tool_calls and content_text:
            head, extracted = _apply_text_tool_calls(content_text)
            if extracted:
                tool_calls = extracted
                content_text = head

        finish_reason = "tool_calls" if (stop_reason == "tool_use" or tool_calls) else "stop"

        message: Dict[str, Any] = {
            "role": "assistant",
            "content": content_text,
        }
        if tool_calls:
            message["tool_calls"] = tool_calls

        return {
            "id": data.get("id", ""),
            "model": data.get("model", ""),
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }],
            "usage": data.get("usage", {}),
        }

    # ── نواة التنفيذ عبر curl ─────────────────────────────────────────────────

    def _curl_args(self, url: str, stream: bool = False) -> List[str]:
        args = ["curl", "-sS", "-X", "POST", url]
        if self.config.follow_redirects:
            # يتبع 301/302/307/308 ويحافظ على الترويسات عند إعادة التوجيه
            args += ["-L", "--location-trusted"]
        if self.config.proxy:
            args += ["-x", self.config.proxy]
        for k, v in self._headers().items():
            args += ["-H", f"{k}: {v}"]
        args += ["--max-time", str(self.config.timeout)]
        # نُرسل البيانات عبر stdin تفادياً لحدود طول سطر الأوامر
        args += ["--data-binary", "@-"]
        if stream:
            args += ["--no-buffer"]
        return args

    async def _run_curl(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST عبر curl مع إعادة محاولة تلقائية للأخطاء العابرة فقط."""
        attempts = max(1, self.config.retries + 1)
        delay = self.config.retry_base
        for i in range(attempts):
            try:
                return await self._run_curl_once(url, payload)
            except TransientProviderError:
                if i >= attempts - 1:
                    raise
                await asyncio.sleep(delay)
                delay *= 2  # تأخير متصاعد
        # لن يصل هنا
        raise ProviderError("❌ فشل غير متوقع في الاتصال.")

    async def _run_curl_once(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """محاولة واحدة عبر curl. يرفع TransientProviderError للأخطاء القابلة للإعادة."""
        args = self._curl_args(url) + ["-w", "\nWEAVER_HTTP_STATUS:%{http_code}"]
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate(input=body)
        except FileNotFoundError:
            raise ProviderError("❌ تعذّر تشغيل curl — تأكد من تثبيته وتوفّره في PATH.")

        if proc.returncode != 0:
            detail = err.decode("utf-8", "replace").strip() or f"رمز الخروج {proc.returncode}"
            msg = (
                f"❌ فشل الاتصال بالمزود ({self.config.base_url}).\n"
                f"   السبب: {detail}\n"
                f"   تلميح: تحقق من الإنترنت أو من صحة WEAVER_BASE_URL "
                f"أو اضبط WEAVER_PROXY إذا كنت خلف بروكسي."
            )
            # أخطاء الشبكة/DNS/المهلة عابرة → أعِد المحاولة
            if proc.returncode in _CURL_TRANSIENT_CODES:
                raise TransientProviderError(msg)
            raise ProviderError(msg)

        raw = out.decode("utf-8", "replace")
        status = 0
        marker = "WEAVER_HTTP_STATUS:"
        if marker in raw:
            raw, _, status_str = raw.rpartition(marker)
            raw = raw.rstrip("\n")
            try:
                status = int(status_str.strip())
            except ValueError:
                status = 0

        self._raise_for_status(status, raw)

        # نحتفظ بآخر استجابة خام للتشخيص (مقتطع محدود)
        self.last_raw = raw[:2000]

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            snippet = raw.strip()[:500] or "(استجابة فارغة)"
            raise ProviderError(
                f"❌ استجابة المزود ليست JSON صالحاً (الحالة {status}).\n"
                f"   المحتوى: {snippet}"
            )

    def _raise_for_status(self, status: int, raw: str) -> None:
        """يرفع خطأً عربياً واضحاً بحسب رمز حالة HTTP"""
        # 2xx فقط نجاح. (0 = curl لم يُبلّغ حالة → نتركه للتحليل اللاحق)
        if status == 0 or 200 <= status < 300:
            return

        # ── 3xx: إعادة توجيه وصلتنا رغم -L (غالباً 305 Use Proxy / بوابة مضغوطة) ──
        # كثيراً ما تردّ بوابة aerolink بـ 305 و«Service Unavailable» تحت الضغط،
        # بينما ينجح نفس الطلب عند إعادة المحاولة. نعامله كخطأ عابر يُعاد تلقائياً.
        if 300 <= status < 400:
            body = raw.strip()[:200] or "(بلا محتوى)"
            # ProviderError (لا Transient) عمداً: لا نُعيد المحاولة على مستوى curl
            # (لا تنجح فوراً وتستنزف التوكينات)؛ سلّم complete() يتكفّل بالتكيّف.
            err3xx = ProviderError(
                f"❌ بوابة المزوّد ردّت بإعادة توجيه/رفض الطلب (HTTP {status}).\n"
                f"   التفصيل: {body}\n"
                f"   تلميح: البوابة ترفض هذا الطلب — يجرّب WeaverCode طلباً أدنى "
                f"تلقائياً. إن تكرّر، فالبوابة مقيّدة؛ جرّب مزوّداً آخر."
            )
            err3xx.status = status
            err3xx.billing = False
            raise err3xx

        snippet = raw.strip()[:400]
        # نحاول استخراج رسالة الخطأ من جسم JSON إن وُجدت
        try:
            j = json.loads(raw)
            err = j.get("error", j)
            if isinstance(err, dict):
                snippet = err.get("message") or err.get("type") or snippet
        except (json.JSONDecodeError, AttributeError):
            pass

        hints = {
            401: "المفتاح WEAVER_API_KEY غير صحيح أو منتهي.",
            403: "المفتاح لا يملك صلاحية للوصول إلى هذا النموذج.",
            404: "المسار أو النموذج غير موجود — تحقق من WEAVER_BASE_URL و WEAVER_MODEL.",
            305: "المزود يطلب استخدام بروكسي (Use Proxy) — اضبط WEAVER_PROXY.",
            307: "إعادة توجيه — تأكد أن follow_redirects مفعّل (WEAVER_FOLLOW_REDIRECTS=true).",
            308: "إعادة توجيه دائمة — تحقق من صحة عنوان الـ URL.",
            429: "تجاوزت حد الطلبات (Rate Limit) — انتظر قليلاً ثم أعد المحاولة.",
            500: "خطأ داخلي في خادم المزود — أعد المحاولة لاحقاً.",
            503: "خدمة المزود غير متاحة حالياً — أعد المحاولة لاحقاً.",
        }
        # كشف رسائل الرصيد/الاشتراك: كثير من المزودين يردّها بحالة 401/403 مضلِّلة
        billing_kw = ("no active free usage", "add balance", "buy a plan",
                      "insufficient", "quota", "billing", "payment required",
                      "credit", "out of usage", "no credit", "رصيد", "اشتراك")
        low = (snippet or "").lower()

        # ── الطلب أكبر من الحدّ (413 أو TPM) → قابل للإصلاح بتقليل max_tokens ──
        too_large_kw = ("request too large", "reduce your message",
                        "tokens per minute", "maximum context",
                        "context length", "too many tokens", "context_length_exceeded")
        if status == 413 or any(k in low for k in too_large_kw):
            lim = re.search(r"limit\s+(\d+)", low)
            req = re.search(r"requested\s+(\d+)", low)
            err = RequestTooLargeError(
                f"❌ الطلب أكبر من حدّ المزوّد (HTTP {status}).\n"
                f"   التفصيل: {snippet}\n"
                f"   تلميح: سيُقلّل WeaverCode حجم الطلب تلقائياً ويعيد المحاولة. "
                f"لتقليل دائم اضبط WEAVER_MAX_TOKENS أصغر (مثلاً 4096).",
                limit=int(lim.group(1)) if lim else 0,
                requested=int(req.group(1)) if req else 0,
            )
            err.status = status
            err.billing = False
            raise err

        is_billing = any(k in low for k in billing_kw)
        if is_billing:
            hint = ("رصيد/اشتراك الحساب لدى المزوّد غير كافٍ أو انتهى الاستخدام "
                    "المجاني — أضف رصيداً أو خطة في لوحة المزوّد، أو جرّب مزوّداً آخر. "
                    "(هذه رسالة من خادم المزوّد لا من مفتاحك.)")
        else:
            hint = hints.get(status, "راجع عنوان المزود والمفتاح والنموذج.")

        err_cls = TransientProviderError if status in _HTTP_TRANSIENT else ProviderError
        err = err_cls(
            f"❌ رفض المزود الطلب (HTTP {status}).\n"
            f"   التفصيل: {snippet}\n"
            f"   تلميح: {hint}"
        )
        # بيانات وصفية ليقرّر الشفاء الذاتي: هل نبدّل الصيغة أم لا؟
        err.status = status
        err.billing = is_billing
        raise err

    # ── الواجهة العامة ────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """
        استدعاء غير متدفق — يُرجع الرد كاملاً بشكل OpenAI الموحّد.

        شفاء ذاتي: إذا فشلت الصيغة المكتشَفة (خطأ دائم غير الرصيد/المصادقة)
        أو أرجعت رداً فارغاً تماماً، يُعاد المحاولة تلقائياً بالصيغة الأخرى
        (Anthropic ↔ OpenAI) ويُتذكَّر ما نجح لبقية الجلسة. هذا يحلّ حالة
        البوابات المتوافقة (مثل capi.aerolink) التي تتكلّم OpenAI لا Anthropic.
        يمكن تعطيل التبديل بتثبيت WEAVER_API_FORMAT صراحةً.
        """
        primary = self._is_anthropic()

        # قاطع الدائرة: بوابة مقيّدة تعلّمنا أنها تقبل «الوضع الأدنى» فقط →
        # نرسل طلباً واحداً أدنى مباشرةً (بلا سلّم) حتى لا نُهدر التوكينات.
        if self._bare_mode:
            return await self._complete_format(messages, None, primary, bare=True)

        # بعض البوابات ترفض طلبات الأدوات؛ إن تعلّمنا ذلك سابقاً في هذه الجلسة
        # نُرسل بلا أدوات مباشرةً (أسرع).
        if self._drop_tools:
            tools = None

        # المستخدم ثبّت الصيغة صراحةً → التزم بها دون سلّم التكيّف.
        if self._format_forced():
            return await self._complete_format(messages, tools, primary)

        # ── سلّم الصمود: جرّب مرشّحين بالترتيب حتى نجاحٍ غير فارغ ────────────
        # كل مرشّح = (الصيغة، هل نرسل الأدوات؟). نغطّي كل ما اكتشفناه من أعطال
        # المزوّدين: صيغة خاطئة (Anthropic↔OpenAI)، بوابة ترفض الأدوات، ردّ فارغ.
        # نتوقّف عند أول ردٍّ حقيقي ونتذكّر ما نجح (صيغة/إسقاط أدوات) لبقية الجلسة.
        candidates = [(primary, True)]
        if tools:
            candidates.append((primary, False))       # أسقط الأدوات (نفس الصيغة)
        candidates.append((not primary, True))         # بدّل الصيغة
        if tools:
            candidates.append((not primary, False))    # بدّل الصيغة + أسقط الأدوات

        last_err: Optional[ProviderError] = None
        first_resp: Optional[Dict[str, Any]] = None

        for fmt, use_tools in candidates:
            t = tools if use_tools else None
            try:
                resp = await self._complete_format(messages, t, fmt)
            except ProviderError as e:
                # الرصيد/المصادقة تفشل بكل المرشّحين → أوقف فوراً (لا تُهدر طلبات)
                if getattr(e, "billing", False) or getattr(e, "status", 0) in (401, 403):
                    raise
                last_err = e
                continue

            if not self._response_is_empty(resp):
                # نجح ردٌّ حقيقي → تعلّم ما نجح (للجلسة وللتشغيلات القادمة)
                if fmt != primary or (tools and not use_tools):
                    if fmt != primary:
                        self._format_override = fmt
                    if tools and not use_tools:
                        self._drop_tools = True
                    self._save_quirk_cache()
                return resp

            # ردٌّ فارغ: احتفظ به كخيار أخير وواصل تجربة المرشّحين
            if first_resp is None:
                first_resp = resp

        # ── احتياط أخير للبوابات المقيّدة (305/3xx): الوضع الأدنى ───────────
        # كثيراً ما ترفض البوابات المجانية البرومبت الطويل (خصوصاً تعليمات
        # «لا تقل إنك Claude») أو الأدوات أو max_tokens الكبير بـ 305. نُجرّب
        # طلباً أدنى يطابق ما ينجح يدوياً: بلا system/tools/temperature وبـ
        # max_tokens صغير. الهوية تبقى محميّة عبر منقّي المخرجات. وعند النجاح
        # نُفعّل قاطع الدائرة فتصير الرسائل التالية طلباً واحداً (لا استنزاف).
        if last_err is not None and 300 <= getattr(last_err, "status", 0) < 400:
            for fmt in (primary, not primary):
                try:
                    resp_bare = await self._complete_format(messages, None, fmt, bare=True)
                except ProviderError:
                    continue
                if not self._response_is_empty(resp_bare):
                    self._bare_mode = True
                    if fmt != primary:
                        self._format_override = fmt
                    self._save_quirk_cache()  # لن نُعيد الاكتشاف مرة أخرى
                    return resp_bare

        # لم ينجح أي مرشّح بردٍّ حقيقي
        if first_resp is not None:
            return first_resp  # أرجِع أفضل ما توفّر (فارغ) بدل رمي خطأ
        raise last_err or ProviderError("❌ فشل كل محاولات الاتصال بالمزوّد.")

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[str, None]:
        """استدعاء متدفق — يُرجع أجزاء النص تباعاً"""
        # صيغة Anthropic: نستخدم الرد الكامل ثم نبثّه دفعة واحدة (أبسط وأكثر موثوقية)
        if self._is_anthropic():
            data = await self.complete(messages, tools)
            text = data["choices"][0]["message"].get("content") or ""
            if text:
                yield text
            return

        # صيغة OpenAI: بثّ SSE حقيقي عبر curl
        payload = self._build_openai_payload(messages, tools, stream=True)
        args = self._curl_args(self._openai_url(), stream=True)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin and proc.stdout
        proc.stdin.write(body)
        await proc.stdin.drain()
        proc.stdin.close()

        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data: "):
                continue
            chunk = line[6:]
            if chunk == "[DONE]":
                break
            try:
                data = json.loads(chunk)
                delta = data["choices"][0]["delta"]
                if delta.get("content"):
                    yield delta["content"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue

        await proc.wait()
        if proc.returncode not in (0, None):
            err = b""
            if proc.stderr:
                err = await proc.stderr.read()
            detail = err.decode("utf-8", "replace").strip() or "خطأ غير معروف"
            raise ProviderError(f"❌ فشل البثّ من المزود: {detail}")

    async def stream_events(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        بثّ مُنمّط على مستوى التوكِن يدعم استدعاءات الأدوات.
        يُنتج أحداثاً:
            {"type": "text", "text": "..."}            نصّ تدريجي (توكِن)
            {"type": "tool_calls", "tool_calls": [...]}  استدعاءات أدوات مكتملة
            {"type": "done", "finish_reason": "..."}    نهاية الدور
        صيغة OpenAI: بثّ SSE حقيقي مع تجميع deltas للأدوات.
        صيغة Anthropic: يعتمد complete() ثم يُصدر الحدث دفعةً (توافق).
        """
        # Anthropic: احتياطي موثوق (SSE الخاص به أعقد)
        if self._is_anthropic():
            data = await self.complete(messages, tools)
            msg = data["choices"][0]["message"]
            if msg.get("content"):
                yield {"type": "text", "text": msg["content"]}
            if msg.get("tool_calls"):
                yield {"type": "tool_calls", "tool_calls": msg["tool_calls"]}
            yield {"type": "done",
                   "finish_reason": data["choices"][0].get("finish_reason", "stop")}
            return

        # OpenAI: بثّ SSE حقيقي
        payload = self._build_openai_payload(messages, tools, stream=True)
        args = self._curl_args(self._openai_url(), stream=True)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        proc = await asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        assert proc.stdin and proc.stdout
        proc.stdin.write(body)
        await proc.stdin.drain()
        proc.stdin.close()

        tool_acc: Dict[int, Dict[str, Any]] = {}   # index -> {id,name,arguments}
        finish = "stop"

        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data: "):
                continue
            chunk = line[6:]
            if chunk == "[DONE]":
                break
            try:
                data = json.loads(chunk)
                choice = data["choices"][0]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
            delta = choice.get("delta", {})
            if delta.get("content"):
                yield {"type": "text", "text": delta["content"]}
            for tcd in delta.get("tool_calls", []) or []:
                idx = tcd.get("index", 0)
                slot = tool_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                if tcd.get("id"):
                    slot["id"] = tcd["id"]
                fn = tcd.get("function", {})
                if fn.get("name"):
                    slot["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["arguments"] += fn["arguments"]

        await proc.wait()

        if tool_acc:
            tool_calls = [{
                "id": v["id"] or f"call_{i}",
                "type": "function",
                "function": {"name": v["name"], "arguments": v["arguments"] or "{}"},
            } for i, v in sorted(tool_acc.items())]
            yield {"type": "tool_calls", "tool_calls": tool_calls}
        yield {"type": "done", "finish_reason": finish}

    async def close(self):
        """موجود للتوافق — لا يوجد اتصال دائم مع curl"""
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class ResilientProvider:
    """
    مزوّد صامد: يجرّب سلسلة مزوّدين بالترتيب.
    إذا فشل الأساسي (نفاد رصيد/مصادقة/شبكة بعد إعادة المحاولة) ينتقل تلقائياً
    للمزوّد الاحتياطي التالي — دون تدخّل المستخدم.
    """

    def __init__(self, providers: List["WeaverProvider"]):
        if not providers:
            raise ProviderError("لا يوجد أي مزوّد مُهيّأ.")
        self.providers = providers

    @property
    def config(self):
        # للبانر/العرض: إعدادات المزوّد الأساسي
        return self.providers[0].config

    @property
    def last_raw(self) -> str:
        """آخر استجابة خام من أي مزوّد فرعي (للتشخيص)."""
        for p in self.providers:
            if getattr(p, "last_raw", ""):
                return p.last_raw
        return ""

    async def complete(self, messages, tools=None):
        errors = []
        for i, p in enumerate(self.providers):
            try:
                return await p.complete(messages, tools)
            except ProviderError as e:
                errors.append(f"[{i+1}] {p.config.base_url}: {str(e).splitlines()[0]}")
                continue
        raise ProviderError("❌ فشل كل المزوّدين:\n   " + "\n   ".join(errors))

    async def stream_events(self, messages, tools=None):
        errors = []
        for i, p in enumerate(self.providers):
            yielded = False
            try:
                async for ev in p.stream_events(messages, tools):
                    yielded = True
                    yield ev
                return
            except ProviderError as e:
                if yielded:
                    raise  # لا يمكن التبديل بعد بدء البثّ
                errors.append(f"[{i+1}] {p.config.base_url}: {str(e).splitlines()[0]}")
                continue
        raise ProviderError("❌ فشل كل المزوّدين:\n   " + "\n   ".join(errors))

    async def stream(self, messages, tools=None):
        async for ev in self.stream_events(messages, tools):
            if ev.get("type") == "text":
                yield ev["text"]

    async def close(self):
        for p in self.providers:
            await p.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


def _load_fallback_configs() -> List[ProviderConfig]:
    """
    تحميل المزوّدين الاحتياطيين من:
    1) config/providers.json → {"fallbacks":[{base_url,api_key,model,...}]}
    2) متغيرات البيئة WEAVER_FALLBACK_BASE_URL / _API_KEY / _MODEL
    """
    fallbacks: List[ProviderConfig] = []

    # (1) ملف providers.json
    from pathlib import Path
    cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "providers.json"
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            for item in data.get("fallbacks", []):
                if not item.get("base_url") or not item.get("api_key"):
                    continue
                fallbacks.append(ProviderConfig(
                    api_key=item["api_key"].strip(),
                    base_url=item["base_url"].strip(),
                    model=(item.get("model") or "").strip(),
                    max_tokens=int(item.get("max_tokens", 8192)),
                    temperature=float(item.get("temperature", 0.7)),
                ))
        except Exception:
            pass

    # (2) متغير بيئة مبسّط لمزوّد احتياطي واحد
    fb_url = os.environ.get("WEAVER_FALLBACK_BASE_URL")
    fb_key = os.environ.get("WEAVER_FALLBACK_API_KEY")
    fb_model = os.environ.get("WEAVER_FALLBACK_MODEL")
    if fb_url and fb_key:
        fallbacks.append(ProviderConfig(
            api_key=fb_key.strip(), base_url=fb_url.strip(),
            model=(fb_model or "").strip(),
        ))
    return fallbacks


def get_provider(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
):
    """
    مصنع مريح للحصول على مزود جاهز.
    الأولوية: المعاملات المباشرة > متغيرات البيئة.
    إذا وُجد مزوّدون احتياطيون (providers.json أو WEAVER_FALLBACK_*) يُرجَع
    ResilientProvider يتنقّل بينهم تلقائياً عند الفشل.
    """
    config = ProviderConfig.from_env()
    if api_key:
        config.api_key = api_key
    if base_url:
        config.base_url = base_url.strip()
    if model:
        config.model = model.strip()
    for k, v in kwargs.items():
        if hasattr(config, k):
            setattr(config, k, v)

    primary = WeaverProvider(config)
    fallbacks = _load_fallback_configs()
    if fallbacks:
        return ResilientProvider([primary] + [WeaverProvider(c) for c in fallbacks])
    return primary
