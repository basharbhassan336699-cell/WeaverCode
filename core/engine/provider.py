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
        )


class ProviderError(RuntimeError):
    """خطأ اتصال أو استجابة من المزود — رسالته عربية واضحة"""


class WeaverProvider:
    """
    موصل عالمي لأي مزود نماذج ذكاء اصطناعي.
    يكتشف صيغة البروتوكول تلقائياً (Anthropic أو OpenAI) وينفّذ عبر curl.
    """

    def __init__(self, config: Optional[ProviderConfig] = None):
        self.config = config or ProviderConfig.from_env()
        if not shutil.which("curl"):
            raise ProviderError(
                "❌ الأداة curl غير مثبّتة على النظام. "
                "ثبّتها أولاً:  sudo apt install curl  (أو pkg install curl على Termux)"
            )

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
        url = self.config.base_url.lower()
        return "aerolink" in url or "anthropic" in url

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
                "x-api-key": self.config.api_key,
                "anthropic-version": "2023-06-01",
                # نُرسل Bearer أيضاً لأن بعض الوسطاء المتوافقين مع Anthropic يقبلونه
                "Authorization": f"Bearer {self.config.api_key}",
            }
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
    ) -> Dict[str, Any]:
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
    def _tools_to_anthropic(tools: List[Dict]) -> List[Dict]:
        """تحويل مخطط أدوات OpenAI إلى مخطط Anthropic"""
        converted = []
        for t in tools:
            fn = t.get("function", t)
            converted.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    def _build_anthropic_payload(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
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

            # رسائل user/assistant النصية العادية
            conv.append({"role": m.role, "content": m.content or ""})

        payload: Dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "messages": conv,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        if tools:
            payload["tools"] = self._tools_to_anthropic(tools)
        if stream:
            payload["stream"] = True
        return payload

    # ── تحويل رد Anthropic إلى شكل OpenAI الموحّد ─────────────────────────────

    @staticmethod
    def _anthropic_to_openai_response(data: Dict[str, Any]) -> Dict[str, Any]:
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        for block in data.get("content", []) or []:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_calls.append({
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input", {}), ensure_ascii=False),
                    },
                })

        stop_reason = data.get("stop_reason", "end_turn")
        finish_reason = "tool_calls" if stop_reason == "tool_use" else "stop"

        message: Dict[str, Any] = {
            "role": "assistant",
            "content": "".join(text_parts) if text_parts else "",
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
        """ينفّذ طلب POST عبر curl ويُرجع الاستجابة كـ JSON (غير متدفق)"""
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
            raise ProviderError(
                f"❌ فشل الاتصال بالمزود ({self.config.base_url}).\n"
                f"   السبب: {detail}\n"
                f"   تلميح: تحقق من الإنترنت أو من صحة WEAVER_BASE_URL "
                f"أو اضبط WEAVER_PROXY إذا كنت خلف بروكسي."
            )

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
        if status and status < 400:
            return

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
        if any(k in low for k in billing_kw):
            hint = ("رصيد/اشتراك الحساب لدى المزوّد غير كافٍ أو انتهى الاستخدام "
                    "المجاني — أضف رصيداً أو خطة في لوحة المزوّد، أو جرّب مزوّداً آخر. "
                    "(هذه رسالة من خادم المزوّد لا من مفتاحك.)")
        else:
            hint = hints.get(status, "راجع عنوان المزود والمفتاح والنموذج.")

        raise ProviderError(
            f"❌ رفض المزود الطلب (HTTP {status}).\n"
            f"   التفصيل: {snippet}\n"
            f"   تلميح: {hint}"
        )

    # ── الواجهة العامة ────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """استدعاء غير متدفق — يُرجع الرد كاملاً بشكل OpenAI الموحّد"""
        if self._is_anthropic():
            payload = self._build_anthropic_payload(messages, tools, stream=False)
            data = await self._run_curl(self._anthropic_url(), payload)
            return self._anthropic_to_openai_response(data)
        else:
            payload = self._build_openai_payload(messages, tools, stream=False)
            return await self._run_curl(self._openai_url(), payload)

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


def get_provider(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    **kwargs,
) -> WeaverProvider:
    """
    مصنع مريح للحصول على مزود جاهز.
    الأولوية: المعاملات المباشرة > متغيرات البيئة.
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
    return WeaverProvider(config)
