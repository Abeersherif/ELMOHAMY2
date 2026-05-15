import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from utils import normalize_arabic_simple as _normalize_arabic_simple

logger = logging.getLogger("mohamy.router")

LLM_TIMEOUT_SECONDS = 20

INTENT_OPTIONS = [
    "specific_law_query",
    "rights_inquiry",
    "procedure_inquiry",
    "definition_query",
    "general",
]


def safe_json_extract(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parsing failed: {e} | RAW: {text[:200]!r}")
        return {}


class RouterAgent:
    """Routes user queries. Async, never throws, always returns structured output."""

    def __init__(self, llm: Optional[ChatGoogleGenerativeAI]):
        self.llm = llm
        if llm is None:
            logger.warning("⚠️ Router Agent initialized in fallback mode (no LLM)")
        else:
            logger.info("✅ Router Agent initialized")

    async def _ainvoke(self, messages, timeout: float = LLM_TIMEOUT_SECONDS):
        if self.llm is None:
            raise RuntimeError("LLM is not configured")
        return await asyncio.wait_for(self.llm.ainvoke(messages), timeout=timeout)

    def _default_classification(self, user_query: str) -> Dict[str, Any]:
        return {
            "intent": "specific_law_query",
            "confidence": 0.4,
            "extracted_info": {
                "law_name": None,
                "category": None,
                "keywords": user_query.split(),
            },
        }

    def _ensure_structure(self, data: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        intent = data.get("intent") or "specific_law_query"
        if intent not in INTENT_OPTIONS:
            intent = "specific_law_query"

        try:
            confidence = float(data.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        extracted = data.get("extracted_info") or {}
        if not isinstance(extracted, dict):
            extracted = {}

        keywords = extracted.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            keywords = user_query.split()

        return {
            "intent": intent,
            "confidence": confidence,
            "extracted_info": {
                "law_name": extracted.get("law_name"),
                "category": extracted.get("category"),
                "keywords": keywords,
            },
        }

    async def classify_query(self, user_query: str) -> Dict[str, Any]:
        if self.llm is None:
            return self._default_classification(user_query)

        intent_list = ", ".join(INTENT_OPTIONS)
        system_prompt = (
            "أنت خبير في تصنيف الأسئلة القانونية. أعد JSON فقط:\n"
            "{\n"
            '  "intent": "<one of: ' + intent_list + '>",\n'
            '  "confidence": 0.0-1.0,\n'
            '  "extracted_info": {"law_name": "...", "category": "...", "keywords": ["..."]}\n'
            "}"
        )
        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=f"السؤال: {user_query}")]
            )
            parsed = safe_json_extract(response.content)
            final = self._ensure_structure(parsed, user_query)
            logger.info(f"🧭 Router: intent={final['intent']} | conf={final['confidence']}")
            return final
        except asyncio.TimeoutError:
            logger.warning("⏱️ Router classify timed out")
            return self._default_classification(user_query)
        except Exception as e:
            logger.error(f"❌ Router classify error: {e}")
            return self._default_classification(user_query)

    async def infer_target_tables(self, user_query: str, all_tables: List[str]) -> List[str]:
        candidates = [
            t for t in all_tables
            if t not in {"قانون", "all_laws", "combined_laws"} and not t.startswith("sqlite_")
        ]
        if not candidates:
            return []

        # ── STRICT match only when the user explicitly names a full law ──
        # e.g. "قانون العقوبات" → match "قانون العقوبات" table.
        # Single-token overlaps like "الدفاع" matching "قانون الدفاع" are
        # dangerous — "الدفاع عن النفس" (self-defense) should go to the
        # penal code, NOT the military defense category.  So we require
        # ALL non-"قانون" tokens of the table name to appear in the query.
        q_tokens = set(_normalize_arabic_simple(user_query).split())

        explicit: List[str] = []
        for table in candidates:
            t_tokens = [t for t in _normalize_arabic_simple(table).split() if t != "قانون"]
            if not t_tokens:
                continue
            overlap = sum(1 for tok in t_tokens if tok in q_tokens)
            # Require FULL overlap — every token of the table name must be
            # in the query.  This prevents single-word false matches.
            if overlap == len(t_tokens):
                explicit.append(table)

        if explicit:
            logger.info(f"🎯 Strict Table Match: {explicit}")
            return explicit

        # ── LLM-based selection — thinks like a smart lawyer ──
        if self.llm is None:
            return []

        return await self._llm_select_tables(user_query, candidates)

    async def _llm_select_tables(self, query: str, available: List[str]) -> List[str]:
        tables_str = "\n".join(f"- {t}" for t in available)
        system_prompt = (
            "أنت محامٍ مصري خبير. مهمتك تحديد أي فروع القانون (الجداول) يجب البحث فيها "
            "للإجابة على سؤال المستخدم.\n\n"
            "**قواعد التفكير:**\n"
            "- فكّر كمحامٍ ذكي: سؤال واحد قد يتطلب البحث في عدة قوانين.\n"
            "  مثال: 'قتلت شخص بدافع الدفاع عن النفس' ← قانون العقوبات + قانون الإجراءات الجنائية.\n"
            "  مثال: 'اترفضت من الشغل' ← قانون العمل + قانون التأمينات الاجتماعية.\n"
            "  مثال: 'ما هي حقوق الزوجة بعد الطلاق' ← قانون الأحوال الشخصية.\n"
            "- لا تختر جدولاً لمجرد تطابق كلمة واحدة. افهم المعنى الكامل.\n"
            "  مثال: 'الدفاع عن النفس' ≠ 'قانون الدفاع' (الأخير عن الدفاع المدني/العسكري).\n"
            "- اختر 1-4 جداول الأكثر صلة بالموضوع القانوني الفعلي.\n\n"
            "**أجب بـ JSON فقط:** [\"اسم الجدول 1\", \"اسم الجدول 2\"]\n"
            "أسماء الجداول يجب أن تكون حرفياً من القائمة المتاحة."
        )
        user_message = (
            f"سؤال المستخدم: \"{query}\"\n\n"
            f"الجداول المتاحة:\n{tables_str}\n\n"
            "اختر الجداول الأنسب قانونياً (ليس بتطابق الكلمات بل بالمعنى القانوني)."
        )
        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
            )
            content = (response.content or "").strip()
            if content.startswith("```"):
                content = re.sub(r"^```\w*\n?", "", content)
                content = re.sub(r"\n?```$", "", content)
            match = re.search(r"\[.*\]", content, re.DOTALL)
            if not match:
                logger.warning("⚠️ LLM returned no JSON list for tables")
                return []
            parsed = json.loads(match.group())
            valid = [t for t in parsed if t in available]
            if not valid:
                logger.warning(f"⚠️ LLM returned tables not in DB: {parsed}")
            else:
                logger.info(f"🤖 AI Selected Tables: {valid}")
            return valid
        except asyncio.TimeoutError:
            logger.warning("⏱️ LLM table selection timed out")
            return []
        except Exception as e:
            logger.error(f"❌ LLM table selection error: {e}")
            return []

    async def reformulate_query(
        self, user_query: str, chat_history: List[Dict[str, str]]
    ) -> str:
        if not chat_history or self.llm is None:
            return user_query

        history_text = "".join(
            f"User: {t.get('user', '')}\nAssistant: {t.get('bot', '')}\n"
            for t in chat_history[-3:]
        )
        system_prompt = (
            "أعد صياغة سؤال المستخدم الأخير ليكون مستقلاً ومفهوماً بناءً على الحوار السابق. "
            "إذا كان السؤال واضحاً ومستقلاً، أعده كما هو. "
            "أعد الصياغة فقط بدون أي مقدمات."
        )
        try:
            response = await self._ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=f"الحوار:\n{history_text}\n\nالسؤال: {user_query}"),
                ]
            )
            new_query = (response.content or "").strip()
            if new_query:
                logger.info(f"🔄 Reformulated: '{user_query}' → '{new_query}'")
                return new_query
            return user_query
        except asyncio.TimeoutError:
            logger.warning("⏱️ Query reformulation timed out")
            return user_query
        except Exception as e:
            logger.error(f"❌ Reformulation error: {e}")
            return user_query
