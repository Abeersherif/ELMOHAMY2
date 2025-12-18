import os
import sqlite3
import logging
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

# Import utilities
from utils import get_connection, list_all_law_tables

# ---------------------------
# Load Gemini API KEY securely
# ---------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("❌ GOOGLE_API_KEY not set! Export it before running.")

# ---------------------------
# Gemini 2.5 Pro LLM
# ---------------------------
from langchain_google_genai import ChatGoogleGenerativeAI

def init_llm():
    """Initialize Gemini 2.0 Flash Exp."""
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        temperature=0.2,
        max_output_tokens=2048,
        convert_system_message_to_human=True,
        google_api_key=GOOGLE_API_KEY
    )

# ---------------------------
# Logging Setup
# ---------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mohamy")

# ---------------------------
# Agents
# ---------------------------
from agents.router_agent import RouterAgent
from agents.retrieval_agent import RetrievalAgent
from agents.answer_agent import AnswerAgent
from agents.knowledge_agent import KnowledgeAgent
# Define DB Path explicitly
DB_PATH = r"D:\law_database.db"

# Initialize Agents
llm = init_llm()
router_agent = RouterAgent(llm)
retrieval_agent = RetrievalAgent(db_path=DB_PATH)
answer_agent = AnswerAgent(llm)
knowledge_agent = KnowledgeAgent(db_path=DB_PATH) # Learns from DB
logger.info("✅ All agents initialized successfully!")

# ---------------------------
# FastAPI App
# ---------------------------
app = FastAPI(title="Mohamy Legal Assistant API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Models
# ---------------------------
class QueryRequest(BaseModel):
    query: str
    session_id: str

class LawArticle(BaseModel):
    id: int
    law_name: Optional[str] = None
    titel: Optional[str] = None
    details: Optional[str] = None
    number: Optional[str] = None
    main_category: Optional[str] = None
    table: Optional[str] = None

class AnswerResponse(BaseModel):
    summary: Optional[str] = None
    steps: Optional[List[str]] = None
    answer: Optional[str] = None
    articles: List[LawArticle] = []
    verification: Dict[str, Any] = {}
    related_topics: List[str] = []
    intent: Optional[str] = None
    source: Optional[str] = None

# ---------------------------
# Endpoints
# ---------------------------

# In-memory history: {session_id: [{"user": "...", "bot": "..."}]}
CHAT_HISTORY: Dict[str, List[Dict[str, str]]] = {}

@app.post("/ask", response_model=Dict[str, Any])
async def ask(request: QueryRequest):
    """
    Main endpoint for legal assistant.
    Orchestrates Router -> Retrieval -> Answer Agent -> Verification.
    """
    try:
        query = request.query
        session_id = request.session_id
        
        logger.info(f"🧑‍⚖️ New Query: {query} [Session: {session_id}]")

        # 0. Contextualize Query (History Handling)
        history = CHAT_HISTORY.get(session_id, [])
        
        # Reformulate query if history exists
        if history:
            processed_query = router_agent.reformulate_query(query, history)
        else:
            processed_query = query
            
        logger.info(f"🗣️ Processed Query: {processed_query}")

        # 1. Step 1: Initial Summary & Steps (Immediate Response)
        
        # 2. Router: Understand Intent & Targets (Use Processed Query)
        # Get all tables first
        all_law_tables = retrieval_agent.law_tables
        
        # Classification
        intent_data = router_agent.classify_query(processed_query)
        intent_label = intent_data.get("intent", "General")
        
        # Infer Targets
        target_tables = router_agent.infer_target_tables(processed_query, all_law_tables)
        
        logger.info(f"🧭 Intent: {intent_label}")
        logger.info(f"🎯 Target tables: {target_tables}")
        
        
        # 3. Retrieval: Get Articles (Use Processed Query)
        if target_tables:
             retrieved_articles = retrieval_agent.retrieve(processed_query, {}, target_tables=target_tables, top_k=30)
        else:
             # Fallback
             retrieved_articles = retrieval_agent.retrieve(processed_query, {}, target_tables=[], top_k=30)

        logger.info(f"📖 Retrieved {len(retrieved_articles)} articles from database")

        # 4. Answer Agent: Verify, Summarize, Answer
        
        # A) Initial Summary (for steps/guidance)
        initial_resp = answer_agent.generate_initial_summary(processed_query)
        
        # B) Verify Articles Relevance
        verification_result = answer_agent.verify_retrieved_articles(processed_query, retrieved_articles)
        filtered_articles = verification_result.get("filtered_articles", [])
        
        # C) Generate Final Answer based on RELEVANT articles
        if filtered_articles:
            articles_to_use = filtered_articles
            source = "database"
        else:
            articles_to_use = []
            source = "llm_only"
            logger.warning("⚠️ Verification failed. Suppressing irrelevant articles.")
        
        # If we have no articles, generate answer from LLM knowledge (fallback)
        if articles_to_use:
            final_answer_text = answer_agent.generate_answer(processed_query, articles_to_use)
        else:
            final_answer_text = answer_agent.generate_fallback_answer(processed_query)
        
        # Update History
        if session_id:
            if session_id not in CHAT_HISTORY:
                CHAT_HISTORY[session_id] = []
            CHAT_HISTORY[session_id].append({"user": query, "bot": final_answer_text})
            # Keep only last 10 turns
            if len(CHAT_HISTORY[session_id]) > 10:
                CHAT_HISTORY[session_id].pop(0)

        # D) Related Topics
        related_topics = answer_agent.suggest_related_topics(processed_query, articles_to_use)
        
        # Construct Response
        response_articles = [
            {
                "id": a.get("id", 0),
                "law_name": f"{a.get('main_category') or a.get('law_name')} - {a.get('titel')}", 
                "titel": a.get("titel"),
                "details": a.get("details"),
                "number": a.get("number"),
                "main_category": a.get("main_category"),
                "table": a.get("table")
            }
            for a in articles_to_use[:5]
        ]

        return {
            "summary": initial_resp.get("summary"),
            "steps": initial_resp.get("steps", []),
            "answer": final_answer_text,
            "articles": response_articles,
            "verification": {
                "verified": verification_result.get("verified", False),
                "message": verification_result.get("message", "تم التحقق"),
                "relevance_score": verification_result.get("relevance_score", 0)
            },
            "related_topics": related_topics,
            "intent": intent_label,
            "source": source,
            "filtered_count": len(filtered_articles),
            "total_articles": len(retrieved_articles),
            "debug_target_tables": target_tables
        }

    except Exception as e:
        logger.error(f"❌ Error processing query: {e}", exc_info=True)
        return {
            "summary": "حدث خطأ أثناء معالجة سؤالك",
            "steps": ["يرجى المحاولة مرة أخرى"],
            "answer": f"عذراً، حدث خطأ في النظام: {str(e)}",
            "articles": [],
            "verification": {"verified": False, "message": "فشل في معالجة الطلب"},
            "related_topics": [],
            "intent": "error",
            "source": "ERROR"
        }


# =======================================================
# Root Endpoint
# =======================================================
@app.get("/")
def home():
    return {"message": "Mohamy Legal Assistant API running successfully 🚀"}


# =======================================================
# Document Upload & OCR Endpoint
# =======================================================
@app.post("/upload_document")
async def upload_document(file: UploadFile = File(...), session_id: str = Form(None)):
    """
    Upload a legal document (PDF, image, or text) for OCR analysis.
    Extracts text and provides legal analysis.
    """
    try:
        logger.info(f"Document Upload: {file.filename} (Type: {file.content_type}) [Session: {session_id}]")
        
        # Read file content
        content = await file.read()
        
        # Analyze document using AnswerAgent
        result = await answer_agent.analyze_document(content, file.filename, file.content_type)
        
        analysis_text = result.get("analysis", "")
        
        # Save to chat history if session_id provided
        if session_id and analysis_text:
            if session_id not in CHAT_HISTORY:
                CHAT_HISTORY[session_id] = []
            CHAT_HISTORY[session_id].append({
                "user": f"تحليل مستند: {file.filename}",
                "bot": analysis_text
            })
            # Keep only last 10 turns
            if len(CHAT_HISTORY[session_id]) > 10:
                CHAT_HISTORY[session_id].pop(0)
            logger.info(f"💾 Document analysis saved to session history [Session: {session_id}]")
        
        return {
            "status": "success",
            "filename": file.filename,
            "analysis": analysis_text,
            "extracted_text": result.get("extracted_text", "")[:500],  # First 500 chars
            "full_text_length": len(result.get("extracted_text", ""))
        }
        
    except Exception as e:
        logger.error(f"❌ Error processing document: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Failed to process document: {str(e)}"
        }


# =======================================================
# Knowledge Browsing Endpoint (Experimental)
# =======================================================
@app.get("/laws")
def get_all_laws():
    """
    Return all laws grouped by category for browsing.
    Uses KnowledgeAgent's in-memory index.
    """
    try:
        data = knowledge_agent.get_all_categories()
        return data  # Returns { categories: [...], total_laws: N }
    except Exception as e:
        logger.error(f"❌ Error fetching law catalog: {e}")
        return {"categories": [], "error": str(e)}
