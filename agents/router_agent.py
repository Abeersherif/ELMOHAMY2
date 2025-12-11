from typing import Dict, Any, List
import logging
import json
import re
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils import normalize_arabic_simple as _normalize_arabic_simple

logger = logging.getLogger("mohamy.router")

def safe_json_extract(text: str) -> Dict[str, Any]:
    """
    Safely extract JSON from LLM response.
    """
    if not text:
        return {}

    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}

    try:
        return json.loads(match.group())
    except Exception as e:
        logger.error(f"❌ JSON parsing failed: {e} | RAW: {text[:200]!r}")
        return {}

class RouterAgent:
    """
    Safer Router Agent:
    - NEVER throws JSON key errors
    - ALWAYS returns complete structure
    """

    def __init__(self, llm: ChatGoogleGenerativeAI):
        self.llm = llm
        logger.info("✅ Router Agent initialized")

    def _ensure_structure(self, data: Dict[str, Any], user_query: str) -> Dict[str, Any]:
        """
        Ensures the output has all required fields.
        Fills missing keys with safe defaults.
        """
        intent = data.get("intent", "specific_law_query")
        confidence = float(data.get("confidence", 0.5))

        extracted = data.get("extracted_info", {})
        if not isinstance(extracted, dict):
            extracted = {}

        extracted_info = {
            "law_name": extracted.get("law_name"),
            "category": extracted.get("category"),
            "keywords": extracted.get("keywords") or user_query.split()
        }

        return {
            "intent": intent,
            "confidence": confidence,
            "extracted_info": extracted_info
        }

    def classify_query(self, user_query: str) -> Dict[str, Any]:
        system_prompt = """أنت خبير في تصنيف الأسئلة القانونية إلى 4 أنواع فقط.

أعد الرد بصيغة JSON فقط:
{
    "intent": "...",
    "confidence": 0.0-1.0,
    "extracted_info": {
        "law_name": "...",
        "category": "...",
        "keywords": ["..."]
    }
}"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"السؤال: {user_query}")
            ]

            response = self.llm.invoke(messages)
            raw = response.content.strip()

            parsed = safe_json_extract(raw)
            final_struct = self._ensure_structure(parsed, user_query)

            logger.info(
                f"🧭 Router: intent={final_struct['intent']} | "
                f"conf={final_struct['confidence']}"
            )

            return final_struct
        except Exception as e:
            logger.error(f"❌ Router classify error: {e}")
            return {
                "intent": "specific_law_query",
                "confidence": 0.4,
                "extracted_info": {
                    "law_name": None,
                    "category": None,
                    "keywords": user_query.split()
                }
            }

    def infer_target_tables(self, user_query: str, all_tables: List[str]) -> List[str]:
        """
        Infer target tables with SMART priority:
        1. Exact/Close Match on explicit Law Name (e.g. "قانون العمل")
        2. LLM Semantic Selection (AI decides based on meaning)
        3. Fallback to broad search
        """
        candidate_tables = [
            t for t in all_tables
            if t not in ["قانون", "all_laws", "combined_laws"] and not t.startswith("sqlite_")
        ]

        if not candidate_tables:
            return []

        q_norm = _normalize_arabic_simple(user_query)
        q_tokens = set(q_norm.split())

        explicit_matches = []
        for table in candidate_tables:
            t_norm = _normalize_arabic_simple(table)
            t_tokens = [t for t in t_norm.split() if t != "قانون"]

            if not t_tokens: continue

            overlap_count = 0
            for token in t_tokens:
                if token in q_tokens:
                    overlap_count += 1

            is_match = False
            if len(t_tokens) == 1:
                if overlap_count == 1: is_match = True
            else:
                if overlap_count == len(t_tokens): is_match = True
                elif len(t_tokens) > 2 and overlap_count >= len(t_tokens) - 1: is_match = True

            if is_match:
                explicit_matches.append(table)

        if explicit_matches:
            logger.info(f"🎯 Strict Table Match: {explicit_matches}")
            return explicit_matches

        return self._llm_select_tables(user_query, candidate_tables)

    def _llm_select_tables(self, query: str, available_tables: List[str]) -> List[str]:
        """
        Ask LLM to pick the most relevant tables for the query.
        """
        tables_str = ", ".join(available_tables)

        system_prompt = """
أنت خبير توجيه قانوني. مهمتك تحديد "الجداول القانونية" (Tables) التي يجب البحث فيها للإجابة على سؤال المستخدم.
لديك قائمة بأسماء الجداول المتاحة في قاعدة البيانات.

المطلوب:
1. فهم موضوع سؤال المستخدم بدقة.
2. اختيار 1 إلى 3 جداول فقط تكون الأكثر صلة بالموضوع.
3. إذا كان السؤال عن "العمل" او "الموظف"، اختر "قانون العمل".
4. إذا كان عن "الزواج/الطلاق"، اختر "قانون الأحوال الشخصية" أو "قانون الأسرة".
5. إذا كان عن "المدني/العقود/التعويض"، اختر "القانون المدني".
6. إذا كان عن "السرقة/القتل/الجريمة"، اختر "قانون العقوبات".

الرد يجب أن يكون قائمة JSON فقط بأسماء الجداول المختارة المطابقة حرفياً للقائمة المتاحة.
Format: ["Table Name 1", "Table Name 2"]
"""

        user_message = f"""
سؤال المستخدم: "{query}"

قائمة الجداول المتاحة:
[{tables_str}]

ما هي الجداول المناسبة للبحث؟ اختر بدقة.
"""
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])

            raw_content = response.content.strip()

            extracted = safe_json_extract(raw_content)

            import json
            import re

            cleaned = raw_content
            if "```" in cleaned:
                cleaned = re.sub(r"```\w*\n", "", cleaned).replace("```", "")

            json_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group())

                validated_tables = []
                for t in params:
                    if t in available_tables:
                        validated_tables.append(t)
                    else:
                        logger.warning(f"⚠️ LLM returned invalid table name: {t}")

                if validated_tables:
                    logger.info(f"🤖 AI Selected Tables: {validated_tables}")
                    return validated_tables

            logger.warning("⚠️ LLM returned no valid JSON list for tables. Falling back.")
            return []

        except Exception as e:
            logger.error(f"❌ Error in AI table selection: {e}")
            return []
