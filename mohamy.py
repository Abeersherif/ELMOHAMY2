import asyncio
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import runtime_store

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mohamy")

# ---------------------------------------------------------------------------
# LLM init — degrade gracefully if GOOGLE_API_KEY is missing
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


def init_llm():
    if not GOOGLE_API_KEY:
        logger.warning(
            "⚠️ GOOGLE_API_KEY not set — running in fallback mode. "
            "Retrieval will work; LLM-powered features will return canned messages."
        )
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.2,
            max_output_tokens=6144,
            convert_system_message_to_human=True,
            google_api_key=GOOGLE_API_KEY,
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize LLM: {e}")
        return None


# ---------------------------------------------------------------------------
# Agents + persistent store
# ---------------------------------------------------------------------------
from agents.router_agent import RouterAgent
from agents.retrieval_agent import RetrievalAgent
from agents.answer_agent import AnswerAgent
from agents.knowledge_agent import KnowledgeAgent

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "law_database.db"))

runtime_store.init_schema()
try:
    runtime_store.cleanup_expired()
except Exception as e:
    logger.error(f"⚠️ Retention cleanup on boot failed: {e}")

llm = init_llm()
router_agent = RouterAgent(llm)
retrieval_agent = RetrievalAgent(db_path=DB_PATH)
answer_agent = AnswerAgent(llm)
knowledge_agent = KnowledgeAgent(db_path=DB_PATH)
logger.info("✅ All agents initialized")


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------
app = FastAPI(title="Mohamy Legal Assistant API")

ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        ",".join([
            "http://localhost:4200",
            "http://127.0.0.1:4200",
            "https://mohamyelmasry.onrender.com",
            "https://mohamy-frontend.onrender.com",
        ]),
    ).split(",")
    if o.strip()
]

# In addition to the explicit ALLOWED_ORIGINS list, accept any Render-hosted
# frontend (https://*.onrender.com). This avoids breakage when the frontend
# service URL changes or when an ALLOWED_ORIGINS env var on the dashboard
# is set without the current frontend origin.
ALLOWED_ORIGIN_REGEX = os.getenv(
    "ALLOWED_ORIGIN_REGEX",
    r"https://([a-z0-9-]+\.)*onrender\.com",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")
    logger.info(f"📁 Serving static files from {STATIC_DIR}")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    query: str
    session_id: str


class ExplainArticleRequest(BaseModel):
    session_id: str
    table: str
    article_id: int


class ConsentRequest(BaseModel):
    session_id: str
    kind: str  # 'privacy' | 'age' | 'cross_border' | 'upload'
    accepted: bool


class ReportRequest(BaseModel):
    session_id: str
    reason: Optional[str] = None
    message_ref: Optional[str] = None


def _shape_article(a: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": a.get("id", 0),
        "law_name": a.get("law_name"),
        "titel": a.get("titel"),
        "details": a.get("details"),
        "number": a.get("number"),
        "main_category": a.get("main_category"),
        "table": a.get("table"),
        "is_cancelled": bool(a.get("is_cancelled")),
        "cancellation_signal": a.get("cancellation_signal") or "",
    }


def _fetch_article_by_ref(table: str, article_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single law article from the law DB by (table, rowid)."""
    if table not in retrieval_agent.law_tables:
        return None
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f'SELECT rowid AS _rid, * FROM "{table}" WHERE rowid = ? LIMIT 1', (article_id,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        cols = row.keys()
        return {
            "id": row["_rid"],
            "table": table,
            "law_name": row["law_name"] if "law_name" in cols else table,
            "titel": row["titel"] if "titel" in cols else "",
            "details": row["details"] if "details" in cols else "",
            "main_category": row["main_category"] if "main_category" in cols else "",
            "number": row["number"] if "number" in cols else None,
        }
    except Exception as e:
        logger.error(f"❌ _fetch_article_by_ref error: {e}")
        return None


# ---------------------------------------------------------------------------
# /ask
# ---------------------------------------------------------------------------
@app.post("/ask")
async def ask(request: QueryRequest) -> Dict[str, Any]:
    t0 = time.monotonic()
    session_id = request.session_id
    query = request.query
    intent_label = "unknown"
    target_tables: List[str] = []
    retrieved: List[Dict[str, Any]] = []
    filtered_articles: List[Dict[str, Any]] = []
    source = "error"

    try:
        logger.info(f"🧑‍⚖️ New Query: {query} [Session: {session_id}]")

        history = runtime_store.recent_turns_for_reformulation(session_id, limit=3)
        processed_query = (
            await router_agent.reformulate_query(query, history) if history else query
        )
        logger.info(f"🗣️ Processed Query: {processed_query}")

        intent_data, target_tables = await asyncio.gather(
            router_agent.classify_query(processed_query),
            router_agent.infer_target_tables(processed_query, retrieval_agent.law_tables),
        )
        intent_label = intent_data.get("intent", "specific_law_query")
        logger.info(f"🧭 Intent: {intent_label} | 🎯 Targets: {target_tables}")

        retrieved = retrieval_agent.retrieve(
            processed_query, {}, target_tables=target_tables, top_k=30
        )
        logger.info(f"📖 Retrieved {len(retrieved)} articles")

        # If user named a specific (article + law/year), pull related judicial rulings
        from utils import extract_legal_refs
        refs = extract_legal_refs(processed_query)
        rulings: List[Dict[str, Any]] = []
        article_numbers = refs.get("article_numbers") or []
        user_cited_articles = bool(article_numbers)  # True only if user typed article nums
        user_law_refs = refs.get("law_refs") or []
        seen_ids: set = set()
        law_existence_warning: Optional[Dict[str, Any]] = None

        def _accumulate(ru):
            for r in ru:
                if r["id"] not in seen_ids:
                    seen_ids.add(r["id"])
                    rulings.append(r)

        # 0) Verify that the law the user cited actually exists. If not, surface
        #    a "did you mean?" warning and use the suggested law for the lookup.
        effective_law_refs = list(user_law_refs)
        if user_law_refs:
            for i, (law_no, year) in enumerate(user_law_refs[:2]):
                try:
                    ln, yr = int(law_no), int(year)
                except (TypeError, ValueError):
                    continue
                if retrieval_agent.verify_law_exists(ln, yr):
                    continue
                # Doesn't exist — find similar
                suggestions = retrieval_agent.find_similar_laws(
                    ln, yr,
                    article_num=int(article_numbers[0]) if article_numbers else None,
                    limit=3,
                )
                if suggestions:
                    if law_existence_warning is None:
                        law_existence_warning = {
                            "user_cited": f"قانون رقم {law_no} لسنة {year}",
                            "exists": False,
                            "suggestions": suggestions,
                        }
                    # Replace this ref with the top suggestion for the rulings lookup
                    top = suggestions[0]
                    effective_law_refs[i] = (str(top["T_No"]), str(top["T_Year"]))
                    logger.info(
                        f"⚠️ Cited law ({law_no}/{year}) does not exist. "
                        f"Using suggested {top['T_No']}/{top['T_Year']} for rulings."
                    )

        # Rulings SQL is heavy (LIKE on 524k rows). Run in a worker thread so
        # it doesn't block the event loop while Gemini calls run in parallel.
        t_rulings = time.monotonic()

        # 1) Strict user-stated refs (with corrections applied)
        if article_numbers and effective_law_refs:
            for (law_no, year) in effective_law_refs[:2]:
                for art in article_numbers[:2]:
                    try:
                        _accumulate(await asyncio.to_thread(
                            retrieval_agent.fetch_rulings_for,
                            int(law_no), int(year), int(art), 6,
                        ))
                    except (TypeError, ValueError):
                        pass
                    if len(rulings) >= 4:
                        break
                if len(rulings) >= 4:
                    break

        # 2) Walk-back fallback — only if strict path returned nothing
        if article_numbers and not rulings and retrieved:
            for art in article_numbers[:2]:
                for cand in retrieved[:3]:
                    pair = retrieval_agent.resolve_law_no_year(cand.get("law_name") or "")
                    if not pair:
                        continue
                    try:
                        _accumulate(await asyncio.to_thread(
                            retrieval_agent.fetch_rulings_for,
                            pair[0], pair[1], int(art), 6,
                        ))
                    except (TypeError, ValueError):
                        pass
                    if rulings:
                        break
                if rulings:
                    break

        # 2b) User didn't cite explicit article numbers but retrieval found
        # specific articles. Seed rulings from the TOP retrieved article(s).
        if not article_numbers and not rulings and retrieved:
            implicit_arts: List[int] = []
            for cand in retrieved[:3]:
                try:
                    n = int(str(cand.get("number") or "").strip())
                    if 1 <= n <= 9999 and n not in implicit_arts:
                        implicit_arts.append(n)
                except (TypeError, ValueError):
                    continue
            if implicit_arts:
                # Promote to article_numbers so downstream steps (topic search
                # and precedent detection) work the same way.
                article_numbers = implicit_arts
                for cand in retrieved[:3]:
                    pair = retrieval_agent.resolve_law_no_year(cand.get("law_name") or "")
                    if not pair:
                        continue
                    try:
                        cand_num = int(str(cand.get("number") or "0"))
                    except (TypeError, ValueError):
                        continue
                    if cand_num not in implicit_arts:
                        continue
                    try:
                        _accumulate(await asyncio.to_thread(
                            retrieval_agent.fetch_rulings_for,
                            pair[0], pair[1], cand_num, 6,
                        ))
                    except (TypeError, ValueError):
                        pass
                    if rulings:
                        logger.info(
                            f"⚖️ Implicit rulings from retrieved article: "
                            f"law={pair[0]}/{pair[1]} art={cand_num}"
                        )
                        break

        # 3) Topic-based supplementary search — needed to surface CONSTITUTIONAL
        #    rulings, which are NOT in the Tash_ahkam link table. Skip only if
        #    we already have a constitutional ruling in `rulings`. Otherwise run
        #    even when many cassation rulings are present — the constitutional
        #    warning depends on this.
        def _has_constitutional(rs):
            for r in rs:
                t = (r.get("titel") or "") + " " + (r.get("snippet") or "")
                if "دستوري" in t or "الدستورية" in t:
                    return True
            return False

        if article_numbers and retrieved and not _has_constitutional(rulings):
            for art in article_numbers[:1]:  # only first article
                for cand in retrieved[:2]:   # only first 2 candidates
                    cand_num = str(cand.get("number") or "").strip()
                    if cand_num != str(art):
                        continue
                    try:
                        extras = await asyncio.wait_for(
                            asyncio.to_thread(
                                retrieval_agent.fetch_rulings_by_article_topic,
                                cand.get("details") or "", int(art), 4,
                            ),
                            timeout=12,
                        )
                        _accumulate(extras)
                        if _has_constitutional(rulings):
                            break
                    except asyncio.TimeoutError:
                        logger.warning("⏱️ topic-based ruling search timed out (12s)")
                        break
                if _has_constitutional(rulings):
                    break

        logger.info(
            f"⚖️ Rulings: {len(rulings)} total in "
            f"{(time.monotonic()-t_rulings)*1000:.0f}ms"
        )

        # Detect cassation/constitutional warnings inside the snippets so we can
        # surface a heads-up even when the article itself isn't flagged as cancelled.
        precedent_warnings = []
        signals = (
            "دستوري", "الدستورية", "مخالف للدستور",  # any form of unconstitutional
            "إسقاط عقوبة", "تقتصر العقوبة", "اقتصرت العقوبة",
            "ملغي", "ملغى", "ملغاة", "مستبدل",
            "مفترضة", "افتراض", "عبء الإثبات",
        )
        for r in rulings[:8]:
            text = ((r.get("snippet") or "") + " " + (r.get("titel") or "")).strip()
            for s in signals:
                if s in text:
                    precedent_warnings.append(
                        f"{r.get('titel') or 'حكم'} ({r.get('date') or ''})"
                    )
                    break
        logger.info(
            f"⚠️ Precedent warnings: {len(precedent_warnings)} of {len(rulings)} rulings flagged"
        )

        # Skip initial summary (frontend treats it as optional).
        initial_resp = {"summary": None, "steps": []}
        related_topics: List[str] = []

        if retrieved:
            t_llm = time.monotonic()
            # Skip verify_retrieved_articles — use top 5 retrieved directly.
            # Saves one full LLM round-trip (~5-15s).
            # BUT: when the user explicitly cited an article number, the precise
            # path returns the right hit at position 1 plus diversified noise
            # (same article number from unrelated tables). Keep only those from
            # the top-scored table to avoid showing irrelevant laws.
            if user_cited_articles and article_numbers and retrieved:
                top = retrieved[0]
                top_table = top.get("table")
                wanted = {str(n) for n in article_numbers}
                same_table_match = [
                    a for a in retrieved
                    if a.get("table") == top_table
                    and str(a.get("number")) in wanted
                ]
                filtered_articles = same_table_match[:3] if same_table_match else [top]
            else:
                # For general queries (no specific article numbers), apply a
                # strict relevance filter before showing articles in the
                # references list.
                #
                # WHY strict?  DB tables are broad *categories* — e.g. the
                # "قانون العمل" table has 6235 rows of miscellaneous laws
                # (military pensions, drug laws, electricity bills …) that
                # merely happen to be filed under that category.  A single
                # keyword like "العمل" matches almost everything because it
                # appears in legal boilerplate ("يعمل به", "استمرار العمل").
                #
                # RULE: require **2+ distinct** non-trivial query tokens to
                # appear in the article's titel OR law_name.  If nothing
                # qualifies → return empty list.  The LLM answer is already
                # good from general knowledge; references are supplementary.
                from utils import normalize_arabic_simple as _norm
                q_norm = _norm(processed_query)
                trivial = {"ما", "هو", "هي", "في", "من", "على", "عن", "هل",
                           "قانون", "قوانين", "مادة", "رقم", "لسنة", "ال",
                           "و", "أن", "ان", "كيف", "اين", "لماذا", "شرح",
                           "اريد", "ابحث", "بخصوص", "حول", "عند", "بعد",
                           "هذا", "هذه", "ذلك", "تلك", "التي", "الذي",
                           "كل", "بعض", "عدم", "يتم", "تم", "بين", "أو",
                           "لا", "لم", "لن", "مع", "إلى", "حتى", "منذ"}
                q_keywords = [w for w in q_norm.split()
                              if w not in trivial and len(w) > 1]
                relevant = []
                for art in retrieved[:20]:
                    # Check ONLY titel (NOT law_name or details — too many false
                    # positives from broad category names and legal boilerplate).
                    art_text = _norm(art.get("titel") or "")
                    required_hits = min(2, len(q_keywords)) if q_keywords else 1
                    hits = sum(1 for kw in q_keywords if kw in art_text)
                    if hits >= required_hits:
                        relevant.append(art)
                    if len(relevant) >= 5:
                        break
                filtered_articles = relevant if relevant else []
            verification = {
                "verified": True,
                "relevance_score": 7,
                "message": "تم اختيار المواد الأعلى صلة من نتائج البحث",
                "filtered_articles": filtered_articles,
            }
            # Generate the final answer directly
            final_answer = await answer_agent.generate_answer(
                processed_query, retrieved,
                rulings=rulings,
                law_correction=law_existence_warning,
            )
            logger.info(f"⏱️ LLM answer: {(time.monotonic()-t_llm)*1000:.0f}ms")
            source = "database"
        else:
            final_answer = await answer_agent.generate_fallback_answer(processed_query)
            verification = {
                "verified": False,
                "relevance_score": 0,
                "message": "لم يتم العثور على مواد قانونية ذات صلة",
                "filtered_articles": [],
            }
            filtered_articles = []
            related_topics = []
            source = "llm_only"

        shaped = [_shape_article(a) for a in filtered_articles[:5]]
        cancelled_warning = bool(verification.get("cancelled_warning")) or any(
            a.get("is_cancelled") for a in filtered_articles
        )
        cancelled_count = sum(1 for a in filtered_articles if a.get("is_cancelled"))

        runtime_store.append_turn(session_id, query, final_answer, articles=shaped)

        latency_ms = int((time.monotonic() - t0) * 1000)
        runtime_store.log_audit(
            event_type="ask",
            session_id=session_id,
            query=query,
            answer_text=final_answer,
            intent=intent_label,
            target_tables=target_tables,
            retrieved=retrieved,
            filtered=filtered_articles,
            rulings=rulings,
            source=source,
            latency_ms=latency_ms,
        )

        return {
            "summary": initial_resp.get("summary"),
            "steps": initial_resp.get("steps", []),
            "answer": final_answer,
            "articles": shaped,
            "verification": {
                "verified": verification.get("verified", False),
                "message": verification.get("message", "تم التحقق"),
                "relevance_score": verification.get("relevance_score", 0),
                "cancelled_warning": cancelled_warning,
                "precedent_warning": bool(precedent_warnings),
                "precedent_refs": precedent_warnings,
                "law_existence_warning": law_existence_warning,
            },
            "related_topics": related_topics,
            "rulings_count": len(rulings),
            "intent": intent_label,
            "source": source,
            "filtered_count": len(filtered_articles),
            "total_articles": len(retrieved),
            "cancelled_count": cancelled_count,
            "debug_target_tables": target_tables,
        }

    except Exception as e:
        logger.error(f"❌ Error processing query: {e}", exc_info=True)
        latency_ms = int((time.monotonic() - t0) * 1000)
        runtime_store.log_audit(
            event_type="ask",
            session_id=session_id,
            query=query,
            intent=intent_label,
            target_tables=target_tables,
            retrieved=retrieved,
            filtered=filtered_articles,
            source="error",
            latency_ms=latency_ms,
            error=str(e),
        )
        return {
            "summary": "حدث خطأ أثناء معالجة سؤالك",
            "steps": ["يرجى المحاولة مرة أخرى"],
            "answer": f"عذراً، حدث خطأ في النظام: {e}",
            "articles": [],
            "verification": {"verified": False, "message": "فشل في معالجة الطلب", "relevance_score": 0},
            "related_topics": [],
            "intent": "error",
            "source": "error",
        }


# ---------------------------------------------------------------------------
# /explain_article — click-to-explain a single law row
# ---------------------------------------------------------------------------
@app.post("/explain_article")
async def explain_article(req: ExplainArticleRequest) -> Dict[str, Any]:
    t0 = time.monotonic()
    try:
        article = _fetch_article_by_ref(req.table, req.article_id)
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")

        explanation = await answer_agent.explain_article(article)
        user_msg = f"عرض شرح: {article.get('titel') or article.get('law_name') or ''}"
        runtime_store.append_turn(req.session_id, user_msg, explanation, articles=[_shape_article(article)])

        latency_ms = int((time.monotonic() - t0) * 1000)
        runtime_store.log_audit(
            event_type="explain",
            session_id=req.session_id,
            query=user_msg,
            answer_text=explanation,
            target_tables=[req.table],
            filtered=[article],
            source="database",
            latency_ms=latency_ms,
        )

        return {
            "explanation": explanation,
            "article": _shape_article(article),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ explain_article error: {e}", exc_info=True)
        latency_ms = int((time.monotonic() - t0) * 1000)
        runtime_store.log_audit(
            event_type="explain",
            session_id=req.session_id,
            query=f"explain {req.table}#{req.article_id}",
            target_tables=[req.table],
            source="error",
            latency_ms=latency_ms,
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# /history — restore chat for a session
# ---------------------------------------------------------------------------
@app.get("/history")
def get_history(session_id: str = Query(...), limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    turns = runtime_store.fetch_history(session_id, limit=limit)
    return {"session_id": session_id, "turns": turns}


@app.delete("/history/last")
def delete_last_turns(
    session_id: str = Query(...),
    count: int = Query(1, ge=1, le=50),
) -> Dict[str, Any]:
    removed = runtime_store.delete_last_turns(session_id, count)
    return {"removed": removed, "session_id": session_id}


# ---------------------------------------------------------------------------
# /sessions — list all chats for the sidebar
# ---------------------------------------------------------------------------
@app.get("/sessions")
def list_sessions(limit: int = Query(50, ge=1, le=200)) -> Dict[str, Any]:
    sessions = runtime_store.list_sessions(limit=limit)
    return {"count": len(sessions), "sessions": sessions}


@app.delete("/sessions/{session_id}")
def delete_session(session_id: str) -> Dict[str, Any]:
    deleted = runtime_store.delete_session(session_id)
    return {"deleted": deleted, "session_id": session_id}


# ---------------------------------------------------------------------------
# /consent — record GDPR/Law-151-style consent
# ---------------------------------------------------------------------------
@app.post("/consent")
def record_consent(req: ConsentRequest, request: Request) -> Dict[str, Any]:
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    runtime_store.record_consent(
        session_id=req.session_id,
        kind=req.kind,
        accepted=req.accepted,
        ip=ip,
        user_agent=ua,
    )
    return {"recorded": True, "kind": req.kind, "accepted": req.accepted}


# ---------------------------------------------------------------------------
# /report — user-flagged bad answer
# ---------------------------------------------------------------------------
@app.post("/report")
def report_answer(req: ReportRequest) -> Dict[str, Any]:
    runtime_store.record_report(
        session_id=req.session_id, reason=req.reason, message_ref=req.message_ref
    )
    return {"recorded": True}


@app.get("/reports")
def list_reports(
    session_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    entries = runtime_store.fetch_reports(session_id=session_id, limit=limit)
    return {"count": len(entries), "reports": entries}


# ---------------------------------------------------------------------------
# /retention/cleanup — manual trigger (also runs on startup)
# ---------------------------------------------------------------------------
@app.post("/retention/cleanup")
def trigger_cleanup() -> Dict[str, Any]:
    deleted = runtime_store.cleanup_expired()
    return {"deleted": deleted}


# ---------------------------------------------------------------------------
# /audit — inspect what happened
# ---------------------------------------------------------------------------
@app.get("/audit")
def get_audit(
    session_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> Dict[str, Any]:
    entries = runtime_store.fetch_audit(session_id=session_id, limit=limit)
    return {"count": len(entries), "entries": entries}


# ---------------------------------------------------------------------------
# /upload_document
# ---------------------------------------------------------------------------
@app.post("/upload_document")
async def upload_document(
    file: UploadFile = File(...), session_id: Optional[str] = Form(None)
) -> Dict[str, Any]:
    t0 = time.monotonic()
    try:
        logger.info(f"📄 Upload: {file.filename} ({file.content_type}) [Session: {session_id}]")
        content = await file.read()
        result = await answer_agent.analyze_document(content, file.filename or "", file.content_type or "")
        analysis_text = result.get("analysis", "")

        if session_id and analysis_text:
            runtime_store.append_turn(
                session_id, f"تحليل مستند: {file.filename}", analysis_text, articles=None
            )

        latency_ms = int((time.monotonic() - t0) * 1000)
        runtime_store.log_audit(
            event_type="upload",
            session_id=session_id,
            query=f"upload {file.filename}",
            answer_text=analysis_text,
            source="document",
            latency_ms=latency_ms,
        )

        return {
            "status": "success",
            "filename": file.filename,
            "analysis": analysis_text,
            "extracted_text": (result.get("extracted_text") or "")[:500],
            "full_text_length": len(result.get("extracted_text") or ""),
        }
    except Exception as e:
        logger.error(f"❌ Document processing error: {e}", exc_info=True)
        latency_ms = int((time.monotonic() - t0) * 1000)
        runtime_store.log_audit(
            event_type="upload",
            session_id=session_id,
            query=f"upload {file.filename}",
            source="error",
            latency_ms=latency_ms,
            error=str(e),
        )
        return {"status": "error", "message": f"Failed to process document: {e}"}


# ---------------------------------------------------------------------------
# /laws — browse categories
# ---------------------------------------------------------------------------
@app.get("/laws")
def get_all_laws() -> Dict[str, Any]:
    try:
        return knowledge_agent.get_all_categories()
    except Exception as e:
        logger.error(f"❌ Error fetching law catalog: {e}")
        return {"categories": [], "error": str(e)}


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "llm_enabled": llm is not None,
        "law_tables": len(retrieval_agent.law_tables),
        "indexed_laws": len(knowledge_agent.law_tables),
    }


# ---------------------------------------------------------------------------
# Root + SPA fallback
# ---------------------------------------------------------------------------
@app.get("/")
def home() -> Dict[str, Any]:
    return {"message": "Mohamy Legal Assistant API running", "docs": "/docs"}


API_ROUTE_PREFIXES = (
    "ask", "upload_document", "laws", "health", "history", "audit", "explain_article",
    "sessions", "consent", "report", "reports", "retention",
    "api", "docs", "openapi.json", "redoc",
)


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith(API_ROUTE_PREFIXES):
        raise HTTPException(status_code=404, detail="Not found")

    if STATIC_DIR.exists():
        static_file = STATIC_DIR / full_path
        if static_file.is_file():
            return FileResponse(static_file)
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

    return {"message": "Mohamy Legal Assistant API running", "docs": "/docs"}
