
import logging
from typing import Dict, List, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger("mohamy.answer")

class AnswerAgent:
    """
    Generates final, simplified, legally-correct answers using Gemini.
    """

    def __init__(self, llm: ChatGoogleGenerativeAI):
        self.llm = llm
        logger.info("✅ Answer Agent initialized")

    def generate_answer(self, user_query: str, retrieved_articles: List[Dict[str, Any]]) -> str:
        """
        Produce the final legal answer that appears to the user
        """

        if not retrieved_articles:
            return "لم أجد مواد قانونية مباشرة حول سؤالك، لكن يمكنني مساعدتك لو شرحت لي التفاصيل أكثر."

        top_context = []
        for i, art in enumerate(retrieved_articles[:5], 1):
            titel = art.get("titel", "")
            details = art.get("details", "")
            law_name = art.get("law_name", "")
            category = art.get("main_category", "")

            top_context.append(
                f"{i}. {law_name} ({category})\n"
                f"العنوان: {titel}\n"
                f"النص: {details[:250]}..."
            )

        context_text = "\n\n".join(top_context)

        system_prompt = """
أنت محامي قانوني مصري خبير ومتخصص. مهمتك تقديم استشارة قانونية شاملة وواضحة.

**هيكل الإجابة المطلوب:**

1. **تحية ومقدمة موجزة** - رحب بالمستخدم وأخبره أنك ستساعده. افصلها بمسافة.

2. **ملخص الموقف القانوني**
   - اكتب العنوان بخط عريض هكذا: **ملخص الموقف القانوني**
   - اترك مسافة فارغة بعد العنوان.
   - اشرح باختصار ما هو الوضع القانوني.

3. **خطوات عملية يجب اتباعها**
   - اكتب العنوان بخط عريض هكذا: **خطوات عملية**
   - اترك مسافة فارغة بعد العنوان.
   - قدم نقاط واضحة ومرقمة.

4. **حقوقك القانونية الأساسية**
   - اكتب العنوان بخط عريض هكذا: **حقوقك القانونية**
   - اترك مسافة فارغة بعد العنوان.
   - اذكر الحقوق على شكل نقاط.

5. **ملاحظة ختامية**
   - اكتب العنوان بخط عريض هكذا: **نصيحة أخيرة**
   - انصح باستشارة محامي.

**تعليمات التنسيق الصارمة:**
- يجب أن تكون العناوين الرئيسية مكتوبة بين نجمتين ** لتظهر بخط عريض.
- **يجب ترك سطر فارغ تماماً** قبل كل عنوان رئيسي وبعده.
- استخدم الرموز النقطية (•) للقوائم.
- ممنوع دمج العنوان مع النص في نفس السطر.
"""

        user_message = f"""
سؤال المستخدم:
{user_query}

المواد القانونية المتوفرة:
{context_text}

قدّم استشارة قانونية شاملة وواضحة باتباع الهيكل المطلوب بالضبط.
"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]

            response = self.llm.invoke(messages)
            answer = response.content.strip()

            import re

            import re

            answer = re.sub(r'([^\n])\n\*\*', r'\1\n\n**', answer)

            answer = re.sub(r'(\*\*.*?\*\*)\n([^\n])', r'\1\n\n\2', answer)

            answer = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', answer)

            answer = answer.replace("* ", "• ")

            return answer

        except Exception as e:
            logger.error(f"❌ Gemini Answer Generation Error: {e}")
            return "حدث خطأ أثناء توليد الإجابة القانونية. برجاء المحاولة مرة أخرى."

    def generate_fallback_answer(self, user_query: str) -> str:
        """
        Used ONLY when DB retrieval = empty.
        Gemini will answer directly from its own general knowledge.
        """
        system_prompt = """
        أنت مساعد قانوني. لم يتم العثور على مواد قانونية في قاعدة البيانات.
        قدم إجابة عامة بناءً على المبادئ القانونية المصرية،
        ولكن بدون الإشارة إلى مواد محددة لأنه لم يتم استرجاع أي منها.
"""

        user_message = f"السؤال: {user_query}"

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])

            if not response or not response.content:
                return "لم أستطع توليد إجابة حالياً. حاول مرة أخرى."

            return response.content.strip()

        except Exception as e:
            logger.error(f"❌ Fallback Gemini error: {e}")
            return "تعذّر توليد إجابة في الوقت الحالي."

    def generate_initial_summary(self, user_query: str) -> Dict[str, Any]:
        """
        Generate initial summary and guidance steps for the user query.

        Args:
            user_query: The user's legal question

        Returns:
            Dictionary containing 'summary' and 'steps'
        """
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

        user_message = f"السؤال القانوني: {user_query}"

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])

            content = response.content.strip()

            import json
            import re

            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "summary": result.get("summary", "تحليل السؤال القانوني"),
                    "steps": result.get("steps", ["استشارة محامي متخصص"])
                }

            return {
                "summary": "سأساعدك في الإجابة على سؤالك القانوني",
                "steps": ["البحث في قاعدة البيانات القانونية", "تحليل المواد المناسبة", "تقديم الإجابة"]
            }

        except Exception as e:
            logger.error(f"❌ Error generating initial summary: {e}")
            return {
                "summary": "سأبحث عن إجابة لسؤالك في قاعدة البيانات القانونية",
                "steps": ["جاري البحث..."]
            }

    def verify_retrieved_articles(self, user_query: str, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verify if the retrieved articles are relevant to the user's query using Gemini.

        Args:
            user_query: The user's question
            articles: List of retrieved articles

        Returns:
            Dictionary with verification status and feedback
        """
        if not articles:
            return {
                "verified": False,
                "message": "لم يتم العثور على مواد قانونية ذات صلة"
            }

        articles_context = []
        for i, art in enumerate(articles[:10], 1):
            law_name = art.get('law_name', 'قانون')
            titel = art.get('titel', '')
            details = art.get('details', '')[:400]
            articles_context.append(
                f"{i}. {law_name}\n"
                f"   العنوان: {titel}\n"
                f"   المحتوى: {details}..."
            )

        context_text = "\n\n".join(articles_context)

        system_prompt = """
أنت خبير قانوني دقيق. مهمتك اختيار المواد التي تجيب **مباشرة** على سؤال المستخدم **المحدد**.

**فهم نية السؤال - هام جداً:**
- "ما هو قانون س؟" → اختر مواد التعريف والشرح (مادة 1-3، التعريفات)
- "ما هي حقوقي في س؟" → اختر مواد الحقوق المحددة، ليس المقدمات
- "ما هي إجراءات س؟" → اختر مواد الإجراءات فقط، ليس المعلومات العامة
- "متى صدر قانون س؟" → يمكن اختيار الديباجة فقط إذا أجابت على هذا

**قاعدة ذهبية:**
لا تختر مادة لمجرد أنها تحتوي على نفس الكلمات. اختر فقط إذا كانت **تجيب** على السؤال.

**مثال توضيحي:**
- السؤال: "ما هو قانون العمل؟"
- ❌ لا تختر: ديباجة (إلا إذا عرّفت نطاق القانون)، مادة 50 عشوائية
- ✅ اختر: مادة 1 (النطاق)، مادة 2 (التعريفات)، مادة 3 (التطبيق)

أجب بصيغة JSON:
{
    "verified": true/false,
    "relevance_score": 0-10,
    "reasoning": "شرح مختصر لماذا هذه المواد تجيب على السؤال",
    "relevant_indices": [2, 3, 5]
}

- verified: true فقط إذا كانت المواد **تجيب** على السؤال المحدد
- relevant_indices: أرقام المواد مرتبة حسب **مدى إجابتها** (الأفضل أولاً)

ردّ بصيغة JSON فقط.
"""

        user_message = f"""
سؤال المستخدم: {user_query}

المواد المرشحة:
{context_text}

اختر المواد التي تجيب **مباشرة** على هذا السؤال المحدد. تجاهل المواد التي تذكر نفس الكلمات فقط دون الإجابة.
"""

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])

            content = response.content.strip()

            import json
            import re
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                relevant_indices = result.get("relevant_indices", [])
                filtered_articles = []

                if relevant_indices:
                    for idx in relevant_indices:
                        if 1 <= idx <= len(articles):
                            filtered_articles.append(articles[idx - 1])

                    logger.info(f"✅ Filtered to {len(filtered_articles)} relevant articles from {len(articles)}")
                else:
                    filtered_articles = articles[:5]

                return {
                    "verified": result.get("verified", len(filtered_articles) >= 3),
                    "relevance_score": result.get("relevance_score", 7),
                    "message": result.get("reasoning") or result.get("message", "تم التحقق من المواد"),
                    "filtered_articles": filtered_articles[:5]
                }

        except Exception as e:
            logger.error(f"❌ Error verifying articles: {e}")
            return {
                "verified": True,
                "relevance_score": 5,
                "message": "تم استرجاع المواد القانونية من قاعدة البيانات"
            }

    def suggest_related_topics(self, user_query: str, articles: List[Dict[str, Any]]) -> List[str]:
        """
        Generate related legal topics the user might be interested in.

        Args:
            user_query: The user's original query
            articles: Retrieved articles

        Returns:
            List of related topic suggestions
        """
        system_prompt = """
أنت خبير قانوني مصري. بناءً على سؤال المستخدم، اقترح مواضيع قانونية ذات صلة قد يرغب في معرفتها.

أعد قائمة من 3-5 مواضيع قانونية ذات صلة بصيغة JSON:
{
    "related_topics": ["موضوع 1", "موضوع 2", "موضوع 3"]
}

ردّ بصيغة JSON فقط.
"""

        user_message = f"السؤال الأصلي: {user_query}"

        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message)
            ])

            content = response.content.strip()

            import json
            import re

            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                topics = result.get("related_topics", [])
                return topics if isinstance(topics, list) else []

            return ["قوانين ذات صلة", "حقوق المواطن", "الإجراءات القانونية"]

        except Exception as e:
            logger.error(f"❌ Error generating related topics: {e}")
            return []

    def generate_complete_response(
        self,
        user_query: str,
        retrieved_articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate the complete response following the full workflow:
        1. Initial summary and steps
        2. Database retrieval (already done)
        3. Verification
        4. Final answer
        5. Related topics

        Args:
            user_query: The user's question
            retrieved_articles: Articles retrieved from the database

        Returns:
            Complete response dictionary
        """
        logger.info("📝 Step 1: Generating initial summary and steps...")
        initial_analysis = self.generate_initial_summary(user_query)

        logger.info("✅ Step 2: Verifying retrieved articles...")
        verification = self.verify_retrieved_articles(user_query, retrieved_articles)

        logger.info("💬 Step 3: Generating final answer...")
        final_answer = self.generate_answer(user_query, retrieved_articles)

        logger.info("🔗 Step 4: Suggesting related topics...")
        related_topics = self.suggest_related_topics(user_query, retrieved_articles)

        return {
            "summary": initial_analysis.get("summary", ""),
            "steps": initial_analysis.get("steps", []),
            "answer": final_answer,
            "verification": verification,
            "related_topics": related_topics,
            "articles_count": len(retrieved_articles)
        }

    async def analyze_document(self, file_content: bytes, filename: str, content_type: str) -> Dict[str, Any]:
        """
        Analyze uploaded document (PDF, image, or text) using Gemini Vision.

        Args:
            file_content: Raw file bytes
            filename: Original filename
            content_type: MIME type

        Returns:
            Dictionary with extracted text and legal analysis
        """
        try:
            import base64
            from PIL import Image
            import io

            extracted_text = ""

            if content_type == "text/plain":
                extracted_text = file_content.decode('utf-8')
                logger.info(f"📝 Extracted {len(extracted_text)} chars from text file")

            elif content_type in ["image/jpeg", "image/png", "image/jpg", "image/webp"]:
                logger.info(f"🖼️ Processing image with Gemini Vision")

                image = Image.open(io.BytesIO(file_content))
                max_size = (1024, 1024)
                if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                    buffer = io.BytesIO()
                    image.save(buffer, format=image.format or 'PNG')
                    file_content = buffer.getvalue()

                image_b64 = base64.b64encode(file_content).decode('utf-8')

                from langchain_core.messages import HumanMessage

                vision_prompt = """
Extract ALL text from this legal document image.
Preserve the original Arabic text exactly as it appears.
Include article numbers, headings, and body text.
Format the output clearly with proper line breaks.
"""

                message = HumanMessage(
                    content=[
                        {"type": "text", "text": vision_prompt},
                        {
                            "type": "image_url",
                            "image_url": f"data:{content_type};base64,{image_b64}"
                        }
                    ]
                )

                response = self.llm.invoke([message])
                extracted_text = response.content.strip()
                logger.info(f"✅ Extracted {len(extracted_text)} chars from image")

            elif content_type == "application/pdf":
                return {
                    "extracted_text": "",
                    "analysis": "دعم ملفات PDF يتطلب مكتبات إضافية. يرجى تحويل الملف إلى صورة أو نص."
                }
            else:
                return {
                    "extracted_text": "",
                    "analysis": f"نوع ملف غير مدعوم: {content_type}. يرجى رفع صور (PNG/JPG) أو ملفات نصية."
                }

            if extracted_text:
                analysis_prompt = f"""
أنت خبير قانوني. حلل نص هذا المستند القانوني وقدم:
1. نوع المستند (قانون، مرسوم، عقد، إلخ)
2. الموضوع الرئيسي
3. النقاط القانونية الرئيسية (3-5 نقاط)
4. أي مواد أو بنود هامة مذكورة

النص:
{extracted_text[:2000]}

قدم التحليل باللغة العربية بشكل واضح ومنظم.
"""

                analysis_response = self.llm.invoke([
                    HumanMessage(content=analysis_prompt)
                ])

                analysis = analysis_response.content.strip()
            else:
                analysis = "لم يتمكن النظام من استخراج نص من المستند."

            return {
                "extracted_text": extracted_text,
                "analysis": analysis
            }

        except Exception as e:
            logger.error(f"❌ Error analyzing document: {e}", exc_info=True)
            return {
                "extracted_text": "",
                "analysis": f"خطأ في معالجة المستند: {str(e)}"
            }

