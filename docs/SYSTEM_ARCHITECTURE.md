# Mohamy Legal Assistant - System Architecture Documentation

## 📋 Table of Contents
1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Technology Stack](#technology-stack)
4. [Agent Architecture](#agent-architecture)
5. [Data Flow](#data-flow)
6. [API Endpoints](#api-endpoints)
7. [Database Schema](#database-schema)
8. [Frontend Architecture](#frontend-architecture)

---

## 🏗️ System Overview

**Mohamy** (محامي) is an AI-powered Egyptian Legal Assistant that provides legal consultation, document analysis, and defense memo drafting capabilities. The system uses a multi-agent architecture powered by Google's Gemini LLM to provide intelligent, context-aware legal responses.

### Key Features:
- 🔍 **Legal Query Processing**: Understands and classifies legal questions
- 📚 **Law Database Search**: Retrieves relevant Egyptian law articles
- 💬 **AI-Powered Responses**: Generates comprehensive legal advice
- 📄 **Document Analysis**: OCR and analysis of legal documents (images/PDFs)
- 📝 **Defense Memo Drafting**: Generates case-specific defense structures
- 🔊 **Voice Input**: Speech recognition for Arabic queries
- 💾 **Session History**: Maintains conversation context

---

## 🎯 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND (Angular)                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  QaComponent (Chat Interface)                                    │   │
│  │  • Text Input / Voice Recognition                                │   │
│  │  • File Upload (Images/PDFs)                                     │   │
│  │  • Chat History Display                                          │   │
│  │  • Related Topics / Law Browsing                                 │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │ HTTP/REST
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI)                               │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                        mohamy.py                                 │   │
│  │  • API Endpoints (/ask, /upload_document, /laws)                 │   │
│  │  • Session Management (CHAT_HISTORY)                             │   │
│  │  • Agent Orchestration                                           │   │
│  └────────────────────────────┬────────────────────────────────────┘   │
│                               │                                         │
│  ┌────────────────────────────▼────────────────────────────────────┐   │
│  │                    MULTI-AGENT SYSTEM                            │   │
│  │                                                                   │   │
│  │  ┌─────────────┐   ┌─────────────┐   ┌─────────────────────┐    │   │
│  │  │   ROUTER    │──▶│  RETRIEVAL  │──▶│      ANSWER         │    │   │
│  │  │    AGENT    │   │    AGENT    │   │      AGENT          │    │   │
│  │  │             │   │             │   │                     │    │   │
│  │  │ • Classify  │   │ • DB Search │   │ • Generate Answer   │    │   │
│  │  │ • Route     │   │ • Keyword   │   │ • Verify Articles   │    │   │
│  │  │ • Reformu-  │   │   Matching  │   │ • Defense Memo      │    │   │
│  │  │   late      │   │             │   │ • Document OCR      │    │   │
│  │  └─────────────┘   └─────────────┘   └──────────────────────┘   │   │
│  │                                                                   │   │
│  │  ┌──────────────────────────────────────────────────────────┐    │   │
│  │  │                   KNOWLEDGE AGENT                         │    │   │
│  │  │  • Law Indexing  • Category Management  • Caching        │    │   │
│  │  └──────────────────────────────────────────────────────────┘    │   │
│  └───────────────────────────────────────────────────────────────────┘   │
│                               │                                          │
│                               ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    EXTERNAL SERVICES                             │    │
│  │  ┌─────────────────┐         ┌─────────────────────────────┐    │    │
│  │  │  SQLite DB      │         │   Google Gemini API         │    │    │
│  │  │  (Egyptian Laws)│         │   (gemini-2.0-flash-exp)    │    │    │
│  │  └─────────────────┘         └─────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

### Backend
| Component | Technology |
|-----------|------------|
| Framework | FastAPI (Python) |
| LLM | Google Gemini 2.0 Flash Exp |
| LLM Framework | LangChain (langchain-google-genai) |
| Database | SQLite |
| Image Processing | Pillow (PIL) |

### Frontend
| Component | Technology |
|-----------|------------|
| Framework | Angular 17+ |
| Styling | CSS (Custom) |
| HTTP Client | Angular HttpClient |
| Speech Recognition | Web Speech API |

---

## 🤖 Agent Architecture

The system uses **4 specialized agents**, each with distinct responsibilities:

### 1. Router Agent (`router_agent.py`)
**Purpose**: Query understanding, classification, and routing

### 2. Retrieval Agent (`retrieval_agent.py`)
**Purpose**: Database search and article retrieval

### 3. Answer Agent (`answer_agent.py`)
**Purpose**: Response generation and document analysis

### 4. Knowledge Agent (`knowledge_agent.py`)
**Purpose**: Law indexing and category management

*(Detailed agent documentation in separate PDF)*

---

## 🔄 Data Flow

### Query Processing Flow:

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────┐
│ 1. SESSION CONTEXT                              │
│    • Load chat history for session_id           │
│    • Reformulate query if history exists        │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│ 2. ROUTER AGENT                                 │
│    • Classify intent (legal query type)         │
│    • Identify target law tables                 │
│    • Extract keywords and concepts              │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│ 3. RETRIEVAL AGENT                              │
│    • Filter by target tables                    │
│    • Keyword matching with scoring              │
│    • Return top-k relevant articles             │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│ 4. ANSWER AGENT                                 │
│    • Verify article relevance                   │
│    • Generate structured response               │
│    • Add defense memo section (if applicable)   │
│    • Suggest related topics                     │
└─────────────────────┬───────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────┐
│ 5. RESPONSE CONSTRUCTION                        │
│    • Format markdown to HTML                    │
│    • Include articles, verification, topics     │
│    • Update session history                     │
└─────────────────────┴───────────────────────────┘
```

---

## 📡 API Endpoints

### `POST /ask`
Main legal consultation endpoint

**Request:**
```json
{
  "query": "ما هو قانون العمل؟",
  "session_id": "web-1234567890"
}
```

**Response:**
```json
{
  "summary": "...",
  "steps": ["..."],
  "answer": "...",
  "articles": [...],
  "verification": { "verified": true, "relevance_score": 8 },
  "related_topics": ["..."],
  "intent": "specific_law_query"
}
```

### `POST /upload_document`
Document upload and analysis

**Request:** Multipart form with:
- `file`: PDF/Image file
- `session_id`: Session identifier

### `GET /laws`
Browse all laws by category

---

## 💾 Database Schema

The SQLite database contains multiple law tables with the following common structure:

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| law_name | TEXT | Name of the law |
| titel | TEXT | Article title |
| details | TEXT | Full article text |
| number | TEXT | Article number |
| main_category | TEXT | Category classification |

---

## 🖥️ Frontend Architecture

### Main Component: `QaComponent`

**Responsibilities:**
- Chat interface management
- Session ID generation/persistence
- File upload handling
- Voice recognition
- Response rendering

**Key Features:**
- Maintains `chatHistory[]` for display
- Sends `session_id` with all requests
- Handles clarification options
- Displays related topics for follow-up

---

## 📁 Project Structure

```
MohamyMasry/
├── mohamy.py                 # Main FastAPI application
├── utils.py                  # Utility functions
├── agents/
│   ├── __init__.py
│   ├── router_agent.py       # Query classification & routing
│   ├── retrieval_agent.py    # Database search
│   ├── answer_agent.py       # Response generation
│   └── knowledge_agent.py    # Law indexing
├── src/
│   └── app/
│       ├── qa/
│       │   ├── qa.component.ts
│       │   ├── qa.component.html
│       │   └── qa.component.css
│       └── services/
├── law_database.db           # SQLite database
└── requirements.txt          # Python dependencies
```

---

*Document Version: 1.0*  
*Last Updated: December 2024*
