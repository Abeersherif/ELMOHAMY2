import asyncio
import base64
import io
import json
import logging
import re
from typing import Any, Dict, List, Optional

from PIL import Image
from langchain_core.messages import HumanMessage, SystemMessage
# pyrefly: ignore [missing-import]
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger("mohamy.answer")

LLM_TIMEOUT_SECONDS = 25
DEFAULT_FALLBACK_ANSWER = "تعذّر توليد إجابة في الوقت الحالي. حاول مرة أخرى لاحقاً."

LEGAL_DISCLAIMER = (
    "\n\n"
    "⚖️ <em>تنبيه: هذه معلومات قانونية عامة مولّدة بواسطة الذكاء الاصطناعي "
    "بناءً على المواد القانونية المسترجعة، وليست استشارة قانونية ولا تغني عن "
    "محامٍ مرخّص. يُرجى التحقق من النصوص القانونية الأصلية ومراجعة محامٍ "
    "قبل اتخاذ أي إجراء.</em>"
)


def _with_disclaimer(text: str) -> str:
    if not text:
        return text
    if "تنبيه: هذه معلومات قانونية عامة" in text:
        return text
    return text + LEGAL_DISCLAIMER


class AnswerAgent:
    """Generates final, legally-correct answers using Gemini (async)."""

    def __init__(self, llm: Optional[ChatGoogleGenerativeAI]):
        self.llm = llm
        if llm is None:
            logger.warning("⚠️ Answer Agent initialized in fallback mode (no LLM available)")
        else:
            logger.info("✅ Answer Agent initialized")

    async def _ainvoke(self, messages, timeout: float = LLM_TIMEOUT_SECONDS):
        if self.llm is None:
            raise RuntimeError("LLM is not configured")
        return await asyncio.wait_for(self.llm.ainvoke(messages), timeout=timeout)

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        if not text:
            return ""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return text.strip()

    @staticmethod
    def _extract_json(text: str) -> Optional[Dict[str, Any]]:
        if not text:
            return None
        cleaned = AnswerAgent._strip_code_fences(text)
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _convert_md_tables(text: str) -> str:
        """Convert Markdown pipe-tables to compact RTL HTML tables."""
        table_re = re.compile(
            r"(?m)^(\|[^\n]+\|\n\|[\s|:\-]+\|\n(?:\|[^\n]+\|\n?)+)"
        )

        def to_html(m: re.Match) -> str:
            block = m.group(1).strip()
            lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
            if len(lines) < 2:
                return block
            headers = [c.strip() for c in lines[0].strip("|").split("|")]
            rows = []
            for ln in lines[2:]:  # skip separator
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if len(cells) == len(headers):
                    rows.append(cells)
            th_style = ("border:1px solid #cbd5e1;padding:6px 10px;"
                        "background:#e2e8f0;text-align:right;font-weight:700")
            td_style = ("border:1px solid #cbd5e1;padding:6px 10px;text-align:right")
            html = ('<table style="border-collapse:collapse;width:100%;'
                    'margin:8px 0;font-size:0.9em" dir="rtl">')
            html += "<thead><tr>"
            for h in headers:
                html += f'<th style="{th_style}">{h}</th>'
            html += "</tr></thead><tbody>"
            for row in rows:
                html += "<tr>"
                for c in row:
                    html += f'<td style="{td_style}">{c}</td>'
                html += "</tr>"
            html += "</tbody></table>"
            return html

        return table_re.sub(to_html, text)

    @staticmethod
    def _format_markdown_response(text: str) -> str:
        if not text:
            return ""

        # Strip triple-backtick code fences — keep the inner content as plain text
        text = re.sub(r"```[\w]*\n?", "", text)
        text = text.replace("```", "")

        text = AnswerAgent._convert_md_tables(text)

        # Strip standalone "---", "***", or "___" separator lines entirely
        text = re.sub(r"(?m)^[-*_]{3,}\s*$", "", text)

        # Ensure blank line BEFORE bold headers, AFTER bold headers
        text = re.sub(r"([^\n])\n\*\*", r"\1\n\n**", text)
        text = re.sub(r"(\*\*.*?\*\*)\n([^\n])", r"\1\n\n\2", text)

        # **Bold** → <strong>
        text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)

        # Bullets: line starting with "* " or "- " → "• "
        text = re.sub(r"(?m)^\s*[*\-]\s+", "• ", text)

        # Collapse 3+ consecutive newlines to exactly 2 (one blank line)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Trim trailing spaces on each line
        text = re.sub(r"[ \t]+\n", "\n", text)

        return text.strip()

    @staticmethod
    def _is_defense_memo_request(query: str) -> bool:
        keywords = [
            "مذكرة دفاع", "مذكره دفاع", "مذكرة الدفاع", "مذكره الدفاع",
            "مذكرات دفاع", "صيغة دفاع", "صيغه دفاع",
        ]
        if any(k in query for k in keywords):
            return True
        if "دفاع" not in query:
            return False
        drafting = ["صيغة", "صيغه", "اعداد", "إعداد", "كتابة", "كتابه",
                    "اكتب", "نموذج", "صياغة", "صياغه", "عن المتهم", "للمتهم"]
        return any(k in query for k in drafting)

    async def generate_initial_summary(self, user_query: str) -> Dict[str, Any]:
        default = {
            "summary": "سأبحث عن إجابة لسؤالك في قاعدة البيانات القانونية",
            "steps": ["جاري البحث في القوانين المصرية...", "تحليل المواد ذات الصلة", "تقديم الإجابة"],
        }
        if self.llm is None:
            return default

        system_prompt = """
أنت خبير قانوني مصري. عند استلام سؤال قانوني:
1. قدم ملخص مختصر لما يسأل عنه المستخدم
2. اقترح خطوات عملية يمكن للمستخدم اتباعها

الصيغة المطلوبة:
{
    "summary": "ملخص مختصر للسؤال",
    "steps": ["خطوة 1", "خطوة 2", "خطوة 3"]
}

ردّ بصيغة JSON فقط.
"""
        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=f"السؤال القانوني: {user_query}")]
            )
            parsed = self._extract_json(response.content)
            if parsed:
                return {
                    "summary": parsed.get("summary") or default["summary"],
                    "steps": parsed.get("steps") or default["steps"],
                }
            return default
        except asyncio.TimeoutError:
            logger.warning("⏱️ Initial summary timed out")
            return default
        except Exception as e:
            logger.error(f"❌ Error generating initial summary: {e}")
            return default

    async def generate_answer(
        self,
        user_query: str,
        retrieved_articles: List[Dict[str, Any]],
        rulings: Optional[List[Dict[str, Any]]] = None,
        law_correction: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Produces the final formatted Arabic legal answer.

        Args:
          rulings: optional list of judicial rulings (from RetrievalAgent.fetch_rulings_for).
                   Each item: {id, titel, date, snippet, linked}.
        """
        if not retrieved_articles:
            return "لم أجد مواد قانونية مباشرة حول سؤالك، لكن يمكنني مساعدتك لو شرحت لي التفاصيل أكثر."

        if self.llm is None:
            return ("النظام يعمل حالياً بدون مفتاح Gemini. "
                    "تم استرجاع المواد القانونية ذات الصلة، يرجى استشارة محامي للحصول على شرح مفصل.")

        top_context = []
        any_cancelled = False
        for i, art in enumerate(retrieved_articles[:5], 1):
            law_name = art.get("law_name", "")
            titel = art.get("titel", "")
            details_full = (art.get("details") or "")[:4000]
            category = art.get("main_category", "")
            status_tag = " [ملغاة]" if art.get("is_cancelled") else ""
            if art.get("is_cancelled"):
                any_cancelled = True
            # IMPORTANT: only pass *hard* cancellation signals to the LLM.
            # Soft signals like "قد تكون تاريخية" cause the model to invent
            # uncertainty warnings. We rely on real proof (linked rulings) instead.
            signal_line = ""
            if art.get("is_cancelled"):
                signal = art.get("cancellation_signal") or ""
                signal_line = f"حالة: {signal}\n" if signal else ""
            top_context.append(
                f"{i}. {law_name}{status_tag} ({category})\n"
                f"العنوان: {titel}\n"
                f"{signal_line}"
                f"النص الكامل: {details_full}"
            )
        context_text = "\n\n".join(top_context)

        is_defense_memo_request = self._is_defense_memo_request(user_query)

        # Detect whether we should switch to "rich" formal-lawyer format:
        # triggered when rulings contain constitutional/cassation signals
        # OR the article is cancelled OR the user asked for a defense memo.
        precedent_signal_words = ("عدم دستوري", "الدستورية", "إسقاط عقوبة",
                                   "تقتصر العقوبة", "ملغي", "ملغى", "مفترضة")
        has_precedent_signal = bool(rulings) and any(
            any(w in (r.get("snippet") or "") + " " + (r.get("titel") or "")
                for w in precedent_signal_words)
            for r in rulings
        )
        use_rich_format = is_defense_memo_request or any_cancelled or has_precedent_signal

        cancellation_block = (
            "\n\n**تحذير حرج — مواد ملغاة أو محكوم بعدم دستوريتها:** يوجد ضمن المواد المعروضة مواد مؤشَّر عليها بـ [ملغاة]. "
            "أشر بوضوح في قسم \"⚠️ تنبيه دستوري/قضائي هام\" إلى الجزء الملغى والقانون البديل (إن وُجد)، "
            "وأكّد على ذلك في بقية الإجابة."
            if any_cancelled else ""
        )

        rulings_block = ""
        rulings_lines = []
        if rulings:
            # Cap at 4 rulings with shorter snippets so the LLM has enough output budget
            for i, r in enumerate(rulings[:4], 1):
                snip = (r.get("snippet") or "").replace("\n", " ").strip()[:280]
                tag = "(مرتبط بالمادة)" if r.get("linked") else "(مرجع بحث)"
                rulings_lines.append(
                    f"{i}. {r.get('titel') or 'حكم'} — {r.get('date') or ''} {tag}\n"
                    f"   ملخص: {snip}..."
                )
            rulings_block = (
                "\n\n**قائمة الأحكام القضائية المتاحة للاستشهاد (مستخرجة من قاعدة البيانات):**\n\n"
                + "\n\n".join(rulings_lines)
                + "\n\n**⚠️ قواعد إلزامية للأحكام:**\n"
                "- استشهد بأرقام الأحكام وتواريخها بدقة كما وردت أعلاه — لا تخترع أرقاماً أو تواريخ.\n"
                "- إذا كان أحد الأحكام صادراً عن المحكمة الدستورية العليا، اذكره بصيغة "
                "  \"قضية رقم X لسنة Y قضائية دستورية - [التاريخ]\".\n"
                "- إذا كان من محكمة النقض، اذكره بصيغة \"الطعن رقم X لسنة Y جلسة [التاريخ]\".\n"
                "- ركّز على الأحكام التي تتضمن إشارات: عدم دستورية، إسقاط عقوبة، تقتصر العقوبة، ملغي، مفترضة، عدم جواز.\n"
                "- لا تذكر أحكاماً لم ترد في القائمة.\n"
                "- **ممنوع الاستنتاج بدون دليل:** لا تستخدم عبارات مثل "
                "\"قد تكون ملغاة\" أو \"قد تكون تاريخية\" أو \"يُحتمل\" أو \"يجب على المستخدم التحقق\" "
                "ما لم تستشهد بحكم قضائي محدد من القائمة. إذا لم تتوفر أحكام دستورية أو "
                "قضائية تثبت الإلغاء، لا تذكر إمكانية الإلغاء أو التعديل إطلاقاً ولا تضع قسم \"تنبيه دستوري/قضائي\"."
            )

        if use_rich_format:
            system_prompt = """
أنت **مساعد قانوني ذكي** مدرَّب على القانون المصري. لست محامياً مرخّصاً ولا تقدّم استشارات قانونية رسمية، بل تقدم **معلومات قانونية عامة** بناءً على المواد المسترجعة من قاعدة البيانات.

هذه القضية تستوجب الهيكل الرسمي المُوسَّع — التزم به حرفياً وبالعناوين كما هي، مع استخدام الرموز التعبيرية (emojis) المحددة.

**هيكل الإجابة الإلزامي:**

(أولاً) ابدأ بسطر تحية واحد دافئ ومختصر يناسب موضوع السؤال:
"أهلاً بك! سأساعدك في فهم [الموضوع] من الناحية القانونية."
ثم اترك سطراً فارغاً.

(ثانياً) **⚖️ [العنوان يعتمد على نوع السؤال — اختر الحالة المناسبة]**

**الحالة أ — سؤال عام عن قانون بأكمله** (مثل: "ما هو قانون الزراعة؟"، "اشرح لي قانون العمل"):
- العنوان: **⚖️ نظرة عامة على [اسم القانون]**
- ابدأ بشرح عام ومبسط: ما هو هذا القانون؟ متى صدر؟ ما الذي ينظمه؟ من يخاطب (مزارعين، عمال، تجار...)؟
- اذكر أهم المحاور والموضوعات التي يغطيها القانون (مثلاً: حماية الأراضي، تنظيم الحيازة، مكافحة الآفات...) — كنقاط مختصرة.
- إذا كانت المواد المسترجعة من قاعدة البيانات تتناول مواد محددة، اذكرها **كأمثلة** داخل الشرح العام وليس كموضوع رئيسي. مثلاً: "ومن أبرز أحكامه أن المادة 152 تحظر البناء على الأراضي الزراعية..."
- **لا تبدأ بشرح مادة محددة** — ابدأ بالقانون ككل ثم أشر للمواد كأمثلة.

**الحالة ب — سؤال عن مادة محددة** (مثل: "ما هي المادة 2 من قانون الزراعة؟"):
- العنوان: **⚖️ شرح المادة [رقم المادة] من [اسم القانون]**
- إذا كانت المادة مرتبطة بأحكام قضائية، أضف سطراً مختصراً:
  "⚠️ توجد أحكام قضائية تؤثر على تطبيق هذه المادة — التفاصيل أدناه."
- **اشرح مضمون المادة بلغة بسيطة وواضحة يفهمها أي شخص** (3-5 جمل). ركّز على: ما هدف المادة؟ من تؤثر عليه؟ ما أثرها العملي؟

**قواعد مشتركة للحالتين:**
- **ممنوع نسخ نص المادة حرفياً بالكامل.** اقتبس فقط الجمل الجوهرية (1-3 جمل كحد أقصى) إذا كانت ضرورية للفهم.
- إذا كانت المادة تحتوي على قوائم طويلة (قوانين ملغاة، بنود متعددة، شروط كثيرة)، **لخّصها** واذكر العدد الإجمالي وأبرز العناصر فقط. لا تدرج القوائم الطويلة بالكامل.
(ثالثاً) **⚠️ تنبيه دستوري/قضائي هام** — يُكتب هذا القسم **فقط** إذا توفرت أحكام دستورية أو قضائية ذات صلة في قائمة الأحكام أعلاه أو إذا كان هناك مواد ملغاة.
- اذكر كل حكم على حدة بصيغة:
  "**الحكم الأول/الثاني/...:** قضت المحكمة الدستورية العليا في القضية رقم X لسنة Y قضائية "دستورية" بجلسة [التاريخ] بـ[ما قُضي به]..."
- اشرح ما الذي قضى به كل حكم وعلى أي مبدأ استند (المتهم بريء، عبء الإثبات، مبدأ شخصية العقوبة...).
- أنهِ القسم بفقرة: "**المعنى العملي:** ..." توضح الأثر المُجمَع لهذه الأحكام على وضع المتهم.

(رابعاً) **📝 صيغة المذكرة القانونية أو الدفاع** — يُكتب هذا القسم **فقط** إذا طلب المستخدم صراحة كتابة صيغة (عريضة دعوى، مذكرة دفاع، شكوى) أو إذا كانت الحالة جنائية واضحة تستلزم ذلك.
- إذا كانت الحالة مدنية/عمالية، استبدل "محكمة جنح مستأنف" بالمحكمة المختصة (مثل المحكمة العمالية أو الابتدائية) واستبدل "المتهم" بـ "المدعي/الشاكي".
- ابدأ برأس المحكمة كنص عادي (ليس داخل code block) واملأ كل البيانات بقيم واقعية افتراضية مستنبطة من سياق السؤال. **يُحظر ترك أي بيان فارغ أو استخدام [...].**
- استخدم هذا الشكل بالضبط كنص عادي:

  [اسم المحكمة المختصة]
  الدائرة [رقم الدائرة]
  في الدعوى/القضية رقم 1234 لسنة 2024

  مذكرة بدفاع / [اسم المستخدم أو صفته: المدعي/الشاكي/المتهم]

  ضد

  [اسم الخصم: النيابة العامة / الشركة / المدعى عليه]

- ثم رتّب الدفوع أو الأسانيد بشكل تحليلي ومفصل بناءً على وقائع قضية المستخدم تحديداً.
- أنهِ بقسم "**الطلبات**" بفقرتين: "**أصلياً:** ..." و"**احتياطياً:** ...". املأ كل البيانات بقيم واقعية مخصصة لحالة المستخدم ولا تترك أي قوس فارغ.

(خامساً) **⏰ الخطوات العملية / الإجراءات القانونية**
- اكتبها كقائمة مرقمة (1. 2. 3. ...) من 4-5 إجراءات.
- كل عنصر يبدأ باسم الإجراء بخط عريض مكتوب بين نجمتين، ثم نقطتان، ثم شرح تفصيلي في جملة أو جملتين. مثال للأسلوب فقط:
  "1. **تقديم الشكوى / رفع الدعوى:** يُرفع خلال [المدة القانونية] أمام [الجهة المختصة]..."
- **لا تستخدم جدول Markdown إطلاقاً** — استخدم القائمة المرقمة فقط.
- خصص الإجراءات والمواعيد على نوع قضية المستخدم (عمالي/مدني/تموين/جنحة) مع المحكمة أو الجهة المختصة.

(سادساً) **📋 الحقوق والمطالبات الممكنة**
- **ملاحظة هامة:** لا تستخدم كلمة "المتهم" إلا في القضايا الجنائية. استخدم (العامل، المالك، المستأجر، المدعي) حسب سياق القضية.
- قسمان فرعيان مختصران:
  • **الحقوق:** 3-4 نقاط بـ "- **اسم الحق:** شرح موجز للحق القانوني لصاحب الشأن".
  • **الطلبات الممكنة:** 3-4 نقاط (تعويض مادي، براءة، إرجاع للعمل، إلغاء قرار، إلخ).
- لا تستخدم جداول Markdown — قوائم نقطية فقط.

(سابعاً) **توصية ختامية**
- جملة أو جملتان بأسلوب ودي: أكّد ضرورة محامٍ مرخّص + أهم النقاط التي يجب أن يتزود بها.



**تعليمات التنسيق والأسلوب:**
- اكتب بأسلوب ودي وبسيط كأنك تشرح لصديق — تجنب اللغة الرسمية الجامدة.
- العناوين الرئيسية بين نجمتين ** مع الرموز التعبيرية (emojis) كما هي موضحة أعلاه.
- سطر فارغ قبل وبعد كل عنوان.
- لا تستخدم لقب "محامي" للإشارة إلى نفسك.
- لا تخترع أحكاماً أو أرقام قضايا — استخدم فقط ما ورد في القائمة المتوفرة.
- إذا لم تتوفر معلومات لقسم ما (مثلاً لم يطلب المستخدم صيغة دفاع)، تجاوزه بأدب.
- **الهدف الأساسي:** أن يخرج المستخدم فاهماً لحقوقه وما يجب عليه فعله، لا أن يقرأ نصوصاً قانونية جافة.

**اكتمال الإجابة:** أكمل جميع الأقسام حتى النهاية. لا تتوقف قبل التوصية الختامية.

**قاعدة عدم التخمين — حرجة:**
- ممنوع كلياً قول "قد تكون المادة ملغاة" أو "قد تكون تاريخية" أو "يُحتمل" أو "يجب على المستخدم التحقق من سريان القانون".
- إذا لم تتوفر لك أحكام دستورية أو قضائية تؤكد الإلغاء (في قائمة الأحكام أعلاه)، **يُحظر** كتابة قسم "تنبيه دستوري/قضائي" أو الإشارة إلى أي شك في سريان المادة.
- المستخدم لا يُكلَّف بالتحقق — أنت من يتحقق ويُقدم الإجابة بأدلة، وإلا فلا تُثِر الموضوع.
""" + cancellation_block + rulings_block + (
                "\n\n**تنبيه تشريعي إلزامي — تصحيح المرجع:**\n"
                f"المستخدم أشار إلى \"{law_correction.get('user_cited')}\" — هذا التشريع غير موجود في قاعدة البيانات. "
                f"التشريع الصحيح المرتبط بالمسألة هو:\n"
                + "\n".join(
                    f"- **القانون رقم {s['T_No']} لسنة {s['T_Year']}** — {s.get('law_name','')}"
                    for s in (law_correction.get("suggestions") or [])[:3]
                )
                + "\n\nاستخدم التشريع الصحيح في رأس الإجابة وفي مذكرة الدفاع وفي كل المراجع. يجب أن يُذكر التصحيح صراحة قبل أي قسم آخر بصياغة مهنية."
                if law_correction else ""
            )
        else:
            system_prompt = """
أنت **مساعد قانوني ذكي** مدرَّب على القانون المصري. لست محامياً مرخّصاً ولا تقدّم استشارات قانونية رسمية، بل تقدم **معلومات قانونية عامة** بناءً على المواد المسترجعة من قاعدة البيانات.

مهمتك تقديم إجابة **شاملة ومفصلة وكاملة** بدون اختصار.

**يجب أن تكتب الأقسام الخمسة كلها بالكامل، ولا تتوقف قبل إكمال جميع الأقسام.**

**قاعدة الأسئلة العامة جداً:**
إذا كان سؤال المستخدم عاماً جداً (مثل: "ما هو قانون العمل؟" أو "ما هو القانون المدني؟") وكانت المواد المسترجعة تتحدث عن قوانين أو قرارات فرعية لا علاقة لها بتعريف الموضوع (مثل قانون التقاعد العسكري أو قوانين أخرى)، **لا تحاول ربطها ببعضها قسراً ولا تدعي أن هذه المواد هي تعريف للقانون**. بدلاً من ذلك، قدم تعريفاً عاماً من معرفتك القانونية العامة للموضوع، ثم أشر باختصار إلى أن "المواد المتاحة حالياً تتناول تطبيقات محددة".

**هيكل الإجابة المطلوب (التزم به حرفياً):**

1. **التحية والمقدمة** - ابدأ بتحية دافئة ومختصرة تناسب الموضوع:
"أهلاً بك! يسعدني مساعدتك في فهم [الموضوع] من الناحية القانونية."
ثم اترك سطر فارغ.

2. **ملخص الموقف القانوني**
   - اكتب العنوان بخط عريض هكذا: **ملخص الموقف القانوني**
   - اترك سطر فارغ بعد العنوان.
   - إذا كان السؤال عاماً والمواد غير مفيدة لتعريفه، قدم تعريفك العام المستقل. أما إذا كانت المواد مفيدة، فاشرح بالإستناد إليها (3-5 جمل) ما هو الإطار التشريعي ذو الصلة.

3. **خطوات عملية يقترحها القانون**
   - اكتب العنوان بخط عريض هكذا: **خطوات عملية**
   - اترك سطر فارغ بعد العنوان.
   - قدم 4-6 خطوات مرقمة واضحة وعملية.

4. **الحقوق ذات الصلة بناءً على المواد المسترجعة**
   - اكتب العنوان بخط عريض هكذا: **الحقوق ذات الصلة**
   - اترك سطر فارغ بعد العنوان.
   - اذكر الحقوق على شكل نقاط (-) مع شرح موجز لكل حق.

5. **توصية ختامية**
   - اكتب العنوان بخط عريض هكذا: **توصية ختامية**
   - اترك سطر فارغ بعد العنوان.
   - أكّد على ضرورة مراجعة **محامٍ مرخّص** قبل اتخاذ أي إجراء، خاصة في الحالات المعقدة.

**تعليمات التنسيق والأسلوب:**
- اكتب بأسلوب ودي وبسيط كأنك تشرح لصديق — تجنب اللغة الرسمية الجامدة.
- **اشرح المواد بلغة بسيطة** — لا تنسخ النصوص القانونية حرفياً. اقتبس فقط الجمل الجوهرية عند الضرورة.
- إذا كانت المادة تحتوي على قوائم طويلة، لخّصها واذكر العدد وأبرز العناصر فقط.
- العناوين بين نجمتين ** لتظهر بخط عريض.
- **سطر فارغ تماماً** قبل وبعد كل عنوان رئيسي.
- استخدم (-) للقوائم النقطية والأرقام للخطوات.
- لا تدمج العنوان مع النص في نفس السطر.
- **لا تستخدم لقب "محامي" للإشارة إلى نفسك. لست محامياً.**
- **لا تختصر، ولا توقف قبل إكمال الأقسام الخمسة كلها.**
- **الهدف الأساسي:** أن يخرج المستخدم فاهماً لحقوقه وما يجب عليه فعله، لا أن يقرأ نصوصاً قانونية جافة.

**قاعدة عدم التخمين — حرجة:**
- ممنوع قول "قد تكون المادة ملغاة" أو "قد تكون تاريخية" أو "يُحتمل" أو "يجب على المستخدم التحقق من سريان القانون".
- إذا لم تتوفر أحكام دستورية/قضائية تؤكد الإلغاء، **لا تُثِر** الموضوع إطلاقاً.
- المستخدم لا يُكلَّف بالتحقق — أنت من يتحقق ويُقدم الإجابة بأدلة.
""" + cancellation_block + rulings_block + (
            "\n\n**تنبيه تشريعي حرج — تصحيح القانون المُستشهَد به:**\n"
            f"المستخدم أشار إلى \"{law_correction.get('user_cited')}\"، وهذا التشريع "
            f"**غير موجود** في قاعدة البيانات الرسمية للقوانين المصرية. "
            f"التشريع الصحيح المرتبط بالموضوع هو:\n"
            + "\n".join(
                f"- **القانون رقم {s['T_No']} لسنة {s['T_Year']}** — {s.get('law_name','')}"
                for s in (law_correction.get("suggestions") or [])[:3]
            )
            + "\n\n**يجب عليك إجبارياً:**\n"
            "- بدء الإجابة بقسم باسم **⚠️ تصحيح المرجع التشريعي** يوضح للمستخدم أن القانون الذي ذكره غير موجود وأن التشريع الصحيح هو ما ورد أعلاه.\n"
            "- استخدام التشريع الصحيح (الرقم والسنة الصحيحين) في جميع أنحاء بقية الإجابة، وعدم تكرار الرقم الخاطئ.\n"
            "- نصح المستخدم بأن أي دفع قانوني مبني على قانون غير موجود سيُرفض شكلاً.\n"
            if law_correction else ""
        )

        user_message = f"""
سؤال المستخدم:
{user_query}

المواد القانونية المتوفرة:
{context_text}

قدّم استشارة قانونية شاملة وواضحة باتباع الهيكل المطلوب بالضبط.
"""

        # Rich format produces a much longer answer (8 sections + tables + memo)
        # so it needs a larger time budget than the default 25s.
        answer_timeout = 90 if use_rich_format else LLM_TIMEOUT_SECONDS

        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_message)],
                timeout=answer_timeout,
            )
            answer = (response.content or "").strip()

            # In rich format the memo section is already included inline.
            # Skip the extra "how-to" addendum to avoid duplication.
            if is_defense_memo_request and not use_rich_format:
                how_to = await self._generate_defense_memo_howto(user_query)
                if how_to:
                    answer = answer + "\n\n" + how_to

            return _with_disclaimer(self._format_markdown_response(answer))
        except asyncio.TimeoutError:
            logger.warning(f"⏱️ generate_answer timed out after {answer_timeout}s")
            return "استغرق التحليل وقتاً أطول من المتوقع. حاول مرة أخرى."
        except Exception as e:
            logger.error(f"❌ Gemini Answer Generation Error: {e}")
            return "حدث خطأ أثناء توليد الإجابة القانونية. برجاء المحاولة مرة أخرى."

    async def _generate_defense_memo_howto(self, query: str) -> str:
        if self.llm is None:
            return ""

        system_prompt = """
أنت **مساعد قانوني ذكي** (لست محامياً). مهمتك تقديم إرشادات تعريفية بسيطة لمحاور الدفاع الممكنة في القضية المذكورة، **بهدف مساعدة المستخدم على الاستعداد لاستشارة محامٍ مرخّص**.

**أسلوب الكتابة:**
- استخدم لغة بسيطة يفهمها غير المتخصص.
- اشرح كل نقطة بوضوح.
- تجنب المصطلحات القانونية المعقدة قدر الإمكان.

**ابدأ مباشرة بدون عناوين رئيسية، واستخدم الهيكل التالي:**

**محاور الدفاع المحتملة:**
- (اشرح بلغة بسيطة المحاور التي يمكن للمحامي البناء عليها)

**المواد القانونية ذات الصلة:**
- (اذكر المواد مع شرح بسيط لكل مادة)

**أمثلة على ما قد يُطلب من المحكمة:**
- (الطلبات بشكل واضح ومفهوم)

**تذكير:** صياغة المذكرة الفعلية يجب أن تتم بواسطة محامٍ مرخّص.
"""
        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt),
                 HumanMessage(content=f"القضية: {query}\n\nقدم إرشادات بسيطة للدفاع في هذه القضية يفهمها أي شخص.")]
            )
            result = (response.content or "").strip()
            return "**كيفية الدفاع في هذه القضية:**\n\n" + result
        except asyncio.TimeoutError:
            logger.warning("⏱️ Defense memo timed out")
            return ""
        except Exception as e:
            logger.error(f"❌ Defense memo error: {e}")
            return (
                "\n**صياغة مذكرة الدفاع:**\n\n"
                "**1. الدفوع القانونية:**\n"
                "   - الدفوع الشكلية (بطلان الإجراءات)\n"
                "   - الدفوع الموضوعية (انتفاء أركان الجريمة)\n\n"
                "**2. السند القانوني:**\n"
                "   - نصوص المواد المؤيدة للدفاع\n\n"
                "**3. الطلبات:**\n"
                "   - طلب البراءة أو رفض الدعوى\n"
            )

    async def generate_fallback_answer(self, user_query: str) -> str:
        if self.llm is None:
            return ("لم يتم العثور على مواد قانونية مباشرة، والنظام يعمل حالياً بدون مفتاح Gemini. "
                    "يرجى استشارة محامي.")

        system_prompt = """
أنت **مساعد قانوني ذكي** مدرَّب على القانون المصري (لست محامياً مرخّصاً).
لم يتم العثور على مواد قانونية محددة في قاعدة البيانات لهذا السؤال، فقدم معلومات عامة استرشادية.

**يجب اتباع هذا الهيكل:**

1. **تحية ومقدمة** (توضح أن الإجابة عامة ولا تستند إلى نص قانوني محدد).

2. **شرح الموقف القانوني العام**
   - العنوان: **ملخص الوضع القانوني**
   - اشرح المبادئ العامة.

3. **خطوات استرشادية**
   - العنوان: **خطوات استرشادية**
   - خطوات عملية.

4. **توصية**
   - العنوان: **توصية**
   - أكّد على ضرورة مراجعة محامٍ مرخّص لعدم توفر النص القانوني الدقيق.

**تعليمات التنسيق:**
- استخدم **للعناوين العريضة**.
- افصل بين الفقرات بأسطر فارغة.
- استخدم النقاط للقوائم.
- **لا تستخدم لقب "محامي" للإشارة إلى نفسك.**
"""
        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=f"السؤال: {user_query}")]
            )
            if not response or not response.content:
                return DEFAULT_FALLBACK_ANSWER
            return _with_disclaimer(self._format_markdown_response(response.content.strip()))
        except asyncio.TimeoutError:
            logger.warning("⏱️ Fallback answer timed out")
            return DEFAULT_FALLBACK_ANSWER
        except Exception as e:
            logger.error(f"❌ Fallback answer error: {e}")
            return DEFAULT_FALLBACK_ANSWER

    async def verify_retrieved_articles(
        self, user_query: str, articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Pick the articles that *answer* the user's question."""
        if not articles:
            return {
                "verified": False,
                "relevance_score": 0,
                "message": "لم يتم العثور على مواد قانونية ذات صلة",
                "filtered_articles": [],
            }
        if self.llm is None:
            return {
                "verified": True,
                "relevance_score": 5,
                "message": "وضع احتياطي بدون LLM",
                "filtered_articles": articles[:5],
            }

        articles_context = []
        for i, art in enumerate(articles[:6], 1):  # was 10; verifier just picks indices
            law_name = art.get("law_name", "قانون")
            titel = art.get("titel", "")
            details = (art.get("details") or "")[:200]  # was 400
            status = " ملغاة" if art.get("is_cancelled") else "✅ سارية"
            articles_context.append(
                f"{i}. {law_name}  [{status}]\n"
                f"   العنوان: {titel}\n"
                f"   المحتوى: {details}..."
            )
        context_text = "\n\n".join(articles_context)

        system_prompt = """
أنت خبير قانوني دقيق. مهمتك اختيار المواد التي تجيب **مباشرة** على سؤال المستخدم **المحدد**.

**قاعدة الإلغاء (حرجة جداً):**
كل مادة معروضة لك تحمل علامة [ ملغاة] أو [✅ سارية].
- **لا تختر مادة ملغاة إلا إذا لم تكن هناك أي مادة سارية تجيب على السؤال.**
- إذا اضطُررت لاختيار مادة ملغاة، يجب أن تذكر ذلك صراحة في `reasoning` بصياغة مثل
  "تنبيه: المادة (X) ملغاة — يُنصح بمراجعة القانون البديل".
- اضبط `cancelled_warning: true` إذا اخترت أي مادة ملغاة، أو إذا كانت كل المواد المتاحة ملغاة.

**فهم نية السؤال - هام جداً:**
- "ما هو قانون س؟" → اختر مواد التعريف والشرح (مادة 1-3، التعريفات)
- "ما هي حقوقي في س؟" → اختر مواد الحقوق المحددة، ليس المقدمات
- "ما هي إجراءات س؟" → اختر مواد الإجراءات فقط، ليس المعلومات العامة

**قاعدة ذهبية:**
لا تختر مادة لمجرد أنها تحتوي على نفس الكلمات. اختر فقط إذا كانت **تجيب** على السؤال **وكانت سارية**.

أجب بصيغة JSON:
{
    "verified": true/false,
    "relevance_score": 0-10,
    "reasoning": "شرح مختصر، اذكر أي تنبيهات إلغاء هنا",
    "relevant_indices": [2, 3, 5],
    "cancelled_warning": true/false
}

ردّ بصيغة JSON فقط.
"""
        user_message = (
            f"سؤال المستخدم: {user_query}\n\n"
            f"المواد المرشحة:\n{context_text}\n\n"
            "اختر المواد التي تجيب **مباشرة** على هذا السؤال المحدد."
        )

        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]
            )
            parsed = self._extract_json(response.content)
            if not parsed:
                logger.warning("⚠️ verify: no JSON parsed; falling back to top 5")
                return {
                    "verified": True,
                    "relevance_score": 5,
                    "message": "تم استرجاع المواد القانونية من قاعدة البيانات",
                    "filtered_articles": articles[:5],
                }

            indices = parsed.get("relevant_indices") or []
            filtered: List[Dict[str, Any]] = []
            for idx in indices:
                try:
                    i = int(idx)
                except (TypeError, ValueError):
                    continue
                if 1 <= i <= len(articles):
                    filtered.append(articles[i - 1])
            if not filtered:
                filtered = articles[:5]

            # Safety net: even if the LLM forgot, flag a warning if any chosen
            # article carries is_cancelled.
            backend_cancel_flag = any(a.get("is_cancelled") for a in filtered[:5])
            cancelled_warning = bool(parsed.get("cancelled_warning")) or backend_cancel_flag

            return {
                "verified": bool(parsed.get("verified", len(filtered) >= 1)),
                "relevance_score": int(parsed.get("relevance_score") or 6),
                "message": parsed.get("reasoning") or "تم التحقق من المواد",
                "filtered_articles": filtered[:5],
                "cancelled_warning": cancelled_warning,
            }
        except asyncio.TimeoutError:
            logger.warning("⏱️ verify_retrieved_articles timed out")
            fallback = articles[:5]
            return {
                "verified": True,
                "relevance_score": 5,
                "message": "انتهت مهلة التحقق",
                "filtered_articles": fallback,
                "cancelled_warning": any(a.get("is_cancelled") for a in fallback),
            }
        except Exception as e:
            logger.error(f"❌ verify_retrieved_articles error: {e}")
            fallback = articles[:5]
            return {
                "verified": True,
                "relevance_score": 5,
                "message": "خطأ في التحقق",
                "filtered_articles": fallback,
                "cancelled_warning": any(a.get("is_cancelled") for a in fallback),
            }

    async def explain_article(self, article: Dict[str, Any]) -> str:
        """Plain-Arabic explanation of a single law article (for click-to-explain UX)."""
        law_name = article.get("law_name") or ""
        category = article.get("main_category") or ""
        titel = article.get("titel") or ""
        details_full = (article.get("details") or "").strip()
        details = details_full[:2500]
        number = article.get("number") or ""

        if not details and not titel:
            return "لا يوجد نص قانوني كافٍ لشرحه."

        if self.llm is None:
            return f"المادة: {titel}\n\n{details}"

        system_prompt = """
أنت **مساعد قانوني ذكي** مدرَّب على القانون المصري (لست محامياً مرخّصاً). اشرح المادة القانونية التالية بلغة عربية بسيطة يفهمها غير المتخصص.

**هيكل الشرح:**

1. **معنى المادة بإيجاز** — اشرح بكلمة واحدة أو جملتين ما الذي تقوله المادة فعلياً.

2. **ماذا تعني للمواطن**
   - العنوان: **ماذا تعني للمواطن**
   - وضح بنقاط (-) كيف تؤثر هذه المادة على حقوق أو واجبات الشخص العادي.

3. **مثال عملي** (إن أمكن)
   - العنوان: **مثال عملي**
   - أعطِ سيناريو واقعي قصير يوضح تطبيق المادة.

4. **ملاحظات قانونية**
   - العنوان: **ملاحظات قانونية**
   - اذكر أي استثناءات أو شروط أو تنبيهات.

**تنسيق:**
- العناوين بين ** **.
- سطر فارغ قبل وبعد كل عنوان.
- نقاط بـ (-).
- لا تكرر النص الأصلي حرفياً — اشرحه.
"""
        user_message = (
            f"القانون: {law_name}\n"
            f"التصنيف: {category}\n"
            f"الرقم: {number}\n"
            f"العنوان: {titel}\n\n"
            f"النص الكامل:\n{details}"
        )
        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_message)],
                timeout=45,
            )
            formatted = self._format_markdown_response((response.content or "").strip())
            if not formatted:
                return f"<strong>{titel}</strong>\n\n{details_full}"
            return _with_disclaimer(formatted)
        except asyncio.TimeoutError:
            logger.warning("⏱️ explain_article timed out (45s)")
            return (
                "<strong>تعذّر توليد الشرح خلال الوقت المتاح. النص الأصلي للمادة:</strong>\n\n"
                f"<strong>{titel}</strong>\n\n{details_full}"
            )
        except Exception as e:
            logger.error(f"❌ explain_article error: {e}")
            return (
                "<strong>تعذّر توليد الشرح. النص الأصلي للمادة:</strong>\n\n"
                f"<strong>{titel}</strong>\n\n{details_full}"
            )

    async def suggest_related_topics(
        self, user_query: str, articles: List[Dict[str, Any]]
    ) -> List[str]:
        if self.llm is None:
            return []
        system_prompt = (
            "أنت خبير قانوني مصري. اقترح 3-5 مواضيع قانونية ذات صلة بسؤال المستخدم.\n"
            'الصيغة JSON فقط: {"related_topics": ["..."]}'
        )
        try:
            response = await self._ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=f"السؤال: {user_query}")]
            )
            parsed = self._extract_json(response.content)
            if parsed:
                topics = parsed.get("related_topics", [])
                return topics if isinstance(topics, list) else []
            return []
        except asyncio.TimeoutError:
            logger.warning("⏱️ Related topics timed out")
            return []
        except Exception as e:
            logger.error(f"❌ Related topics error: {e}")
            return []

    async def analyze_document(
        self, file_content: bytes, filename: str, content_type: str
    ) -> Dict[str, Any]:
        try:
            extracted_text = ""

            if content_type == "text/plain":
                extracted_text = file_content.decode("utf-8", errors="replace")
                logger.info(f"📝 Extracted {len(extracted_text)} chars from text file")

            elif content_type in {"image/jpeg", "image/png", "image/jpg", "image/webp"}:
                if self.llm is None:
                    return {"extracted_text": "",
                            "analysis": "تحليل الصور يحتاج إلى مفتاح Gemini مفعل."}

                image = Image.open(io.BytesIO(file_content))
                if image.size[0] > 1024 or image.size[1] > 1024:
                    image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
                    buf = io.BytesIO()
                    image.save(buf, format=image.format or "PNG")
                    file_content = buf.getvalue()

                image_b64 = base64.b64encode(file_content).decode("utf-8")
                vision_message = HumanMessage(
                    content=[
                        {"type": "text", "text":
                            "Extract ALL Arabic text from this legal document image. "
                            "Preserve original wording, article numbers, headings."},
                        {"type": "image_url",
                         "image_url": f"data:{content_type};base64,{image_b64}"},
                    ]
                )
                response = await self._ainvoke([vision_message], timeout=40)
                extracted_text = (response.content or "").strip()
                logger.info(f"✅ Extracted {len(extracted_text)} chars from image")

            elif content_type == "application/pdf":
                return {"extracted_text": "",
                        "analysis": "دعم ملفات PDF يتطلب مكتبات إضافية. "
                                    "يرجى تحويل الملف إلى صورة أو نص."}
            else:
                return {"extracted_text": "",
                        "analysis": f"نوع ملف غير مدعوم: {content_type}. "
                                    "يرجى رفع صور (PNG/JPG) أو ملفات نصية."}

            if not extracted_text:
                return {"extracted_text": "",
                        "analysis": "لم يتمكن النظام من استخراج نص من المستند."}

            if self.llm is None:
                return {"extracted_text": extracted_text,
                        "analysis": "تم استخراج النص، لكن التحليل غير متاح بدون مفتاح Gemini."}

            analysis_prompt = f"""
أنت **مساعد قانوني ذكي** مدرَّب على القانون المصري (لست محامياً مرخّصاً). حلل نص هذا المستند وقدم تقريراً تعريفياً.

**هيكل التقرير:**

1. **(بدون عنوان) افتتاحية مباشرة**
   - ابدأ بـ "أهلاً بك، بصفتي مساعدك القانوني الذكي..." مباشرة دون كتابة "تحية".

2. **ملخص المستند**
   - اشرح نوع المستند وموضوعه باختصار.

3. **النقاط الرئيسية**
   - استخرج أهم البنود (التواريخ، المبالغ، الشروط).

4. **تنبيهات تستحق المراجعة**
   - اذكر أي بنود قد تنطوي على مخاطر أو غموض، **بصياغة وصفية لا توجيهية**.

5. **توصية**
   - أكّد على ضرورة مراجعة محامٍ مرخّص قبل توقيع أو الاعتماد على المستند.

**تعليمات التنسيق:**
- لا تكتب كلمة "تحية" أو "مقدمة" كعنوان. ابدأ بالنص فوراً.
- العناوين الرئيسية محاطة بـ **.
- استخدم النقاط (-) للقوائم.
- **لا تستخدم لقب "محامي" للإشارة إلى نفسك.**

النص المستخرج من المستند:
{extracted_text[:3000]}
"""
            analysis_response = await self._ainvoke(
                [HumanMessage(content=analysis_prompt)], timeout=40
            )
            analysis = _with_disclaimer(
                self._format_markdown_response((analysis_response.content or "").strip())
            )
            return {"extracted_text": extracted_text, "analysis": analysis}

        except asyncio.TimeoutError:
            logger.warning("⏱️ Document analysis timed out")
            return {"extracted_text": "", "analysis": "انتهت مهلة تحليل المستند."}
        except Exception as e:
            logger.error(f"❌ Document analysis error: {e}", exc_info=True)
            return {"extracted_text": "", "analysis": f"خطأ في معالجة المستند: {e}"}
