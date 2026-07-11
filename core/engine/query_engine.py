"""
query_engine.py — محرك الحلقة الوكيلية الرئيسية لـ WeaverCode
ينظم: إرسال الرسائل ← استقبال الرد ← تنفيذ الأدوات ← إرسال النتائج ← تكرار
"""

import asyncio
import json
import uuid
from typing import AsyncGenerator, Callable, Dict, Any, List, Optional
from dataclasses import dataclass, field

from .provider import WeaverProvider, Message, get_provider
from ..tools.registry import ToolRegistry
from ..memory.store import MemoryStore


@dataclass
class QueryResult:
    text: str
    tool_calls_made: List[str] = field(default_factory=list)
    turns: int = 0
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    error: Optional[str] = None


class QueryEngine:
    """
    قلب WeaverCode — ينفذ حلقة الوكيل:
    prompt → think → tool_call → result → think → ... → final_answer
    """

    MAX_TURNS = 20

    def __init__(
        self,
        provider: Optional[WeaverProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
        memory: Optional[MemoryStore] = None,
        system_prompt: Optional[str] = None,
        max_turns: int = MAX_TURNS,
    ):
        self.provider = provider or get_provider()
        self.tools = tool_registry or ToolRegistry()
        self.memory = memory or MemoryStore()
        self.system_prompt = system_prompt or self._default_system()
        self.max_turns = max_turns

    def _default_system(self) -> str:
        """البروموه الافتراضي — يستعمل بروموه الوضع الرئيسي مع قلب الهوية.

        نستورد get_system_prompt بشكل كسول لتفادي أي اعتماد دائري ولضمان
        أن يبقى الوكيل معرِّفاً عن نفسه كـ WeaverCode حتى دون تمرير بروموه.
        """
        try:
            from prompts.system import get_system_prompt
            return get_system_prompt("main")
        except Exception:
            # احتياطي مضمون: هوية WeaverCode صريحة
            return (
                "أنت WeaverCode، وكيل برمجي ذكي ومستقل.\n"
                "اسمك WeaverCode فقط. إذا سُئلت من أنت فأجب: «أنا WeaverCode».\n"
                "ممنوع أن تقول إنك Claude أو Anthropic أو GPT أو أي شركة أو نموذج،\n"
                "وممنوع كشف النموذج أو المزوّد الذي يشغّلك. لغتك الافتراضية العربية."
            )

    async def run(
        self,
        prompt: str,
        history: Optional[List[Message]] = None,
        on_text: Optional[Callable[[str], None]] = None,
        on_tool: Optional[Callable[[str, Dict], None]] = None,
    ) -> QueryResult:
        """
        تشغيل الحلقة الوكيلية الكاملة
        
        Args:
            prompt: المهمة المطلوبة
            history: سجل المحادثة السابق
            on_text: callback عند وصول نص
            on_tool: callback عند تنفيذ أداة
        Returns:
            QueryResult مع النتيجة النهائية
        """
        messages: List[Message] = []

        # إضافة السياق من الذاكرة
        memory_context = await self.memory.get_relevant(prompt)
        system = self.system_prompt
        if memory_context:
            system += f"\n\n## ذاكرة ذات صلة:\n{memory_context}"

        messages.append(Message(role="system", content=system))

        # إضافة السجل السابق
        if history:
            messages.extend(history)

        messages.append(Message(role="user", content=prompt))

        tools_schema = self.tools.get_schema()
        result = QueryResult(text="")
        turns = 0

        while turns < self.max_turns:
            turns += 1

            try:
                response = await self.provider.complete(messages, tools=tools_schema)
            except Exception as e:
                result.error = str(e)
                break

            choice = response["choices"][0]
            msg = choice["message"]
            finish_reason = choice.get("finish_reason", "stop")

            # إضافة رد المساعد للسجل
            assistant_msg = Message(
                role="assistant",
                content=msg.get("content") or "",
                tool_calls=msg.get("tool_calls"),
            )
            messages.append(assistant_msg)

            # نص وصل؟
            if msg.get("content") and on_text:
                on_text(msg["content"])

            # لا توجد أدوات للتنفيذ؟
            if finish_reason == "stop" or not msg.get("tool_calls"):
                result.text = msg.get("content") or ""
                break

            # تنفيذ الأدوات
            tool_results = []
            for tc in msg["tool_calls"]:
                tool_name = tc["function"]["name"]
                tool_id = tc["id"]
                try:
                    args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    args = {}

                result.tool_calls_made.append(tool_name)

                if on_tool:
                    on_tool(tool_name, args)

                try:
                    tool_output = await self.tools.execute(tool_name, args)
                except Exception as e:
                    tool_output = f"خطأ في تنفيذ {tool_name}: {e}"

                tool_results.append(
                    Message(
                        role="tool",
                        content=str(tool_output),
                        tool_call_id=tool_id,
                        name=tool_name,
                    )
                )

            messages.extend(tool_results)

        result.turns = turns

        # حفظ في الذاكرة
        await self.memory.save(prompt, result.text, result.tool_calls_made)

        return result

    async def stream_run(
        self,
        prompt: str,
        history: Optional[List[Message]] = None,
    ) -> AsyncGenerator[str, None]:
        """نسخة متدفقة — تُرجع النص كلمة كلمة"""
        messages = [
            Message(role="system", content=self.system_prompt),
            Message(role="user", content=prompt),
        ]
        if history:
            messages[1:1] = history

        async for chunk in self.provider.stream(messages):
            yield chunk
