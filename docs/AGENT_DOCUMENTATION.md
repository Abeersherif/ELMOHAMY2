# Mohamy Legal Assistant - Agent Documentation

## Complete Guide to All System Agents

---

# 📋 Table of Contents

1. [Router Agent](#1-router-agent)
2. [Retrieval Agent](#2-retrieval-agent)
3. [Answer Agent](#3-answer-agent)
4. [Knowledge Agent](#4-knowledge-agent)

---

# 1. Router Agent

**File Location:** `agents/router_agent.py`  
**Purpose:** Query understanding, classification, and intelligent routing

## Overview

The Router Agent is the **first point of contact** for any user query. It acts as the "brain" that understands what the user is asking and determines where to look for answers. Think of it as a smart receptionist who listens to your question and directs you to the right department.

## Key Responsibilities

| Responsibility | Description |
|----------------|-------------|
| Query Classification | Determines what type of legal question is being asked |
| Table Selection | Identifies which law databases to search |
| Query Reformulation | Incorporates conversation history for context |

---

## Methods Explained

### `__init__(self, llm)`
**What it does:** Initializes the Router Agent with the Gemini LLM.

**In simple terms:** Sets up the agent with the AI brain it needs to understand questions.

---

### `classify_query(self, user_query: str) → Dict`
**What it does:** Analyzes the user's question and classifies it into categories.

**How it works:**
1. Sends the query to Gemini with a classification prompt
2. Gemini returns a JSON with:
   - `intent`: Type of query (e.g., "specific_law_query", "general_legal_advice")
   - `confidence`: How sure the AI is (0.0 to 1.0)
   - `extracted_info`: Keywords, law names, categories detected

**Example:**
```
Input: "ما هي حقوق العامل في قانون العمل؟"
Output: {
    "intent": "specific_law_query",
    "confidence": 0.9,
    "extracted_info": {
        "law_name": "قانون العمل",
        "category": "حقوق العمال",
        "keywords": ["حقوق", "العامل", "قانون العمل"]
    }
}
```

---

### `infer_target_tables(self, user_query: str, all_tables: List[str]) → List[str]`
**What it does:** Determines which database tables (laws) to search based on the query.

**How it works (3-step priority system):**

1. **Exact Match First:** Looks for explicit law names in the query
   - If user says "قانون العمل", it directly matches to the "قانون العمل" table
   
2. **LLM Semantic Selection:** If no exact match, asks Gemini to pick relevant tables
   - Gemini analyzes the meaning and selects 1-3 most relevant tables
   
3. **Fallback:** If nothing matches, searches all tables

**Example:**
```
Query: "حقوق الموظف المفصول"
Step 1: No exact "قانون" name found
Step 2: LLM selects → ["قانون العمل", "قانون التأمينات الاجتماعية"]
Result: Search these 2 tables only
```

**Why this matters:** Instead of searching 50+ law tables, we narrow down to 2-3 relevant ones, making search faster and more accurate.

---

### `_llm_select_tables(self, query: str, available_tables: List[str]) → List[str]`
**What it does:** Asks Gemini to intelligently select the most relevant database tables.

**The prompt tells Gemini:**
- "العمل" or "الموظف" → suggest "قانون العمل"
- "الزواج/الطلاق" → suggest "قانون الأحوال الشخصية"
- "السرقة/القتل" → suggest "قانون العقوبات"
- "العقود/التعويض" → suggest "القانون المدني"

---

### `reformulate_query(self, user_query: str, chat_history: List) → str`
**What it does:** Makes a follow-up question standalone by adding context from previous messages.

**Why needed:** Users often ask follow-up questions like "ما هي عقوبتها؟" which makes no sense without knowing what "ها" refers to.

**How it works:**
1. Takes the last 3 conversation turns
2. Asks Gemini to rewrite the current query as a complete question
3. Returns the reformulated query

**Example:**
```
Previous: "أريد رفع دعوى طلاق"
Current: "كم تتكلف؟"
Reformulated: "كم تكلفة رفع دعوى الطلاق؟"
```

---

### `_ensure_structure(self, data: Dict, user_query: str) → Dict`
**What it does:** Safety function that ensures the output always has all required fields.

**Why needed:** LLM responses can be unpredictable. This function guarantees a consistent structure even if Gemini returns incomplete data.

---

### `safe_json_extract(text: str) → Dict`
**What it does:** Safely extracts JSON from LLM responses, handling markdown code blocks and errors.

**Handles cases like:**
```
```json
{"intent": "query"}
```
```
→ Extracts: `{"intent": "query"}`

---

# 2. Retrieval Agent

**File Location:** `agents/retrieval_agent.py`  
**Purpose:** Database search and article retrieval

## Overview

The Retrieval Agent is the **database expert**. It knows how to search through thousands of Egyptian law articles and find the most relevant ones for the user's question. Think of it as a librarian who knows exactly where every law book is and can find the right pages quickly.

## Key Responsibilities

| Responsibility | Description |
|----------------|-------------|
| Database Connection | Connects to SQLite law database |
| Table Discovery | Automatically finds all law tables |
| Keyword Search | Finds articles matching query terms |
| Relevance Scoring | Ranks articles by relevance |

---

## Methods Explained

### `__init__(self, db_path: str)`
**What it does:** Initializes the agent and loads all law data into memory.

**On startup:**
1. Connects to the SQLite database
2. Discovers all law tables (names containing "قانون")
3. Loads all articles into memory for fast searching
4. Creates a searchable corpus

---

### `_discover_law_tables(self) → List[str]`
**What it does:** Automatically finds all valid law tables in the database.

**Filtering logic:**
- ✅ Include: Tables containing "قانون" or "قوانين"
- ❌ Exclude: "sqlite_" system tables
- ❌ Exclude: "tash_" tables
- ❌ Exclude: Master tables like "combined_laws", "all_laws"
- ❌ Exclude: Generic tables exactly named "قانون"

**Example result:** `["قانون العمل", "قانون العقوبات", "قانون الأحوال الشخصية", ...]`

---

### `_load_all_law_texts(self) → Tuple[List, List]`
**What it does:** Loads all law articles into memory with their full text.

**For each article, stores:**
- `law_name`: Name of the law
- `table`: Source table name
- `titel`: Article title
- `details`: Full article text
- `main_category`: Category classification
- `full_text`: Combined searchable text

**Returns:**
- `semantic_laws`: List of article dictionaries
- `semantic_corpus`: List of searchable text strings

---

### `retrieve(self, user_query: str, ..., target_tables: List[str], top_k: int) → List[Dict]`
**What it does:** Main search function that finds relevant articles.

**How it works:**

1. **Filter by Target Tables**
   - If tables specified, only search those
   - Otherwise, search all loaded articles

2. **Normalize Query**
   - Remove Arabic diacritics (تشكيل)
   - Normalize different forms of letters (أ/ا, ة/ه, ي/ى)
   - Remove punctuation

3. **Remove Stopwords**
   - Filters out common words like: ما، هو، في، من، على، كيف، هل
   - Keeps only meaningful search terms

4. **Score Each Article**
   - Title match: +10 points per keyword
   - Text match: +1 point per occurrence + 1 bonus

5. **Sort and Return**
   - Sorts by score (highest first)
   - Returns top_k results (default: 20)

**Example scoring:**
```
Query: "حقوق العامل"
Article: "قانون العمل - مادة 5 - حقوق العمال الأساسية"
Score: 10 (title) + 5 (text occurrences) = 15
```

---

### `_keyword_search(self, query: str, top_k: int) → List[Dict]`
**What it does:** Simple keyword-based search fallback.

**Simpler than `retrieve()`** - just counts word matches without advanced scoring.

---

### `_normalize_arabic_simple(text: str) → str`
**What it does:** Normalizes Arabic text for better matching.

**Transformations:**
- Removes: diacritics (ً ٌ ٍ), tatweel (ـ), punctuation
- Normalizes: أ/إ/آ → ا, ة → ه, ى → ي
- Converts to lowercase

**Example:**
```
Input: "القانونُ المَدَنِيّ"
Output: "القانون المدني"
```

---

# 3. Answer Agent

**File Location:** `agents/answer_agent.py`  
**Purpose:** Response generation, verification, and document analysis

## Overview

The Answer Agent is the **main communicator**. It takes the retrieved law articles and generates human-readable, helpful legal advice. It also handles document analysis (OCR) and special features like defense memo drafting. Think of it as the actual lawyer who explains the law to you in simple terms.

## Key Responsibilities

| Responsibility | Description |
|----------------|-------------|
| Answer Generation | Creates structured legal responses |
| Article Verification | Checks if retrieved articles are truly relevant |
| Defense Memo Drafting | Generates case-specific defense structures |
| Document Analysis | OCR and analysis of uploaded documents |
| Related Topics | Suggests follow-up questions |

---

## Methods Explained

### `__init__(self, llm)`
**What it does:** Initializes the Answer Agent with the Gemini LLM.

---

### `generate_answer(self, user_query: str, retrieved_articles: List) → str`
**What it does:** Creates the main legal response the user sees.

**Response Structure (enforced by prompt):**
1. **تحية ومقدمة** - Greeting and brief intro
2. **ملخص الموقف القانوني** - Legal situation summary
3. **خطوات عملية** - Practical steps to take
4. **حقوقك القانونية** - User's legal rights
5. **نصيحة أخيرة** - Final advice

**Special Feature - Defense Memo Detection:**
- Checks if query mentions "مذكرة دفاع" or defense-related terms
- If detected, automatically appends "كيفية الدفاع في هذه القضية" section

**Process:**
1. Formats top 5 articles as context
2. Sends to Gemini with structured prompt
3. Formats markdown response for HTML display
4. Adds defense memo section if applicable

---

### `_is_defense_memo_request(self, query: str) → bool`
**What it does:** Detects if the user is asking about drafting a defense.

**Detection patterns:**
- **Direct matches:** مذكرة دفاع، صيغة دفاع
- **Contextual matches:** "دفاع" + (صيغة/اعداد/كتابة/عن المتهم/للمتهم)

**Examples that trigger it:**
- ✅ "اريد مذكرة دفاع"
- ✅ "صيغة دفاع عن المتهم"
- ✅ "اعداد دفاع في قضية سرقة"
- ❌ "ما هي حقوق الدفاع؟" (asking about rights, not drafting)

---

### `_generate_defense_memo_howto(self, query: str) → str`
**What it does:** Generates a case-specific defense structure using the LLM.

**Output structure:**
- **ما يمكن الدفاع به:** Case-specific defense points
- **المواد القانونية المفيدة:** Relevant law articles with simple explanations
- **ماذا نطلب من المحكمة:** Specific requests

**Key feature:** Content is tailored to the specific case mentioned in the query, not generic.

---

### `verify_retrieved_articles(self, user_query: str, articles: List) → Dict`
**What it does:** Uses AI to check if retrieved articles actually answer the question.

**Why needed:** Keyword matching can return articles that contain the same words but don't actually answer the question.

**Process:**
1. Sends query + top 10 articles to Gemini
2. Gemini evaluates each article for relevance
3. Returns:
   - `verified`: True/False
   - `relevance_score`: 0-10
   - `filtered_articles`: Only the truly relevant ones
   - `relevant_indices`: Which articles to use

**Example:**
```
Query: "ما هو قانون العمل؟"
Retrieved: [ديباجة، مادة 50، مادة 1، مادة 2]
Filtered: [مادة 1 (scope), مادة 2 (definitions)]
```

---

### `generate_initial_summary(self, user_query: str) → Dict`
**What it does:** Creates a quick summary and steps before the main answer.

**Returns:**
```json
{
    "summary": "سأساعدك في معرفة حقوق العمال...",
    "steps": ["البحث في قانون العمل", "تحديد المواد المناسبة", "تقديم الإجابة"]
}
```

---

### `suggest_related_topics(self, user_query: str, articles: List) → List[str]`
**What it does:** Generates related topics the user might want to explore.

**Returns 3-5 related topics like:**
- "حقوق الموظف المفصول"
- "إجراءات الشكوى العمالية"
- "التعويضات المقررة"

---

### `generate_fallback_answer(self, user_query: str) → str`
**What it does:** Generates an answer when no database articles are found.

**Used when:** Database search returns empty results.  
**Source:** Gemini's general legal knowledge (not from database).  
**Includes:** Disclaimer that the answer is general guidance.

---

### `analyze_document(self, file_content: bytes, filename: str, content_type: str) → Dict`
**What it does:** Analyzes uploaded legal documents (images, PDFs).

**Supported formats:**
- Images: JPEG, PNG, WebP → Uses Gemini Vision for OCR
- Text: Plain text → Direct processing
- PDF: Returns message about format limitations

**Process for images:**
1. Resize large images to 1024x1024 max
2. Convert to base64
3. Send to Gemini Vision with Arabic OCR prompt
4. Extract text and analyze for legal content

**Analysis includes:**
- Document type identification
- Key points extraction (dates, amounts, conditions)
- Legal warnings
- Legal opinion

---

### `_format_markdown_response(self, text: str) → str`
**What it does:** Converts markdown formatting to HTML-friendly format.

**Transformations:**
- `**Bold**` → `<strong>Bold</strong>`
- `* ` → `• ` (bullet points)
- Ensures proper spacing around headers

---

# 4. Knowledge Agent

**File Location:** `agents/knowledge_agent.py`  
**Purpose:** Law indexing, categorization, and caching

## Overview

The Knowledge Agent is the **memory and organizer**. It builds and maintains an index of all laws, their categories, and subjects. It also handles caching to improve performance. Think of it as the card catalog system in a library that helps you find books by category or subject.

## Key Responsibilities

| Responsibility | Description |
|----------------|-------------|
| Law Indexing | Creates searchable indexes of all laws |
| Category Management | Organizes laws by categories |
| Subject Extraction | Identifies subjects/topics from titles |
| Caching | Refreshes knowledge cache periodically |

---

## Methods Explained

### `__init__(self, db_path: str, cache_refresh_minutes: int = 60)`
**What it does:** Initializes the agent and performs first knowledge refresh.

**Stores:**
- `law_tables`: List of law table names
- `law_metadata`: Detailed info about each law
- `all_categories`: Categories mapped to laws
- `all_subjects`: Extracted subject keywords
- `law_stats`: Article counts per law

---

### `refresh_knowledge(self)`
**What it does:** Rebuilds the entire knowledge index from the database.

**Process:**
1. Discover all law tables
2. Index each table (metadata, categories, subjects)
3. Build category-to-law mappings
4. Update last refresh timestamp

**When called:**
- On initialization
- When cache expires (default: 60 minutes)

---

### `_discover_law_tables(self, conn) → List[str]`
**What it does:** Finds all tables starting with "قانون".

**Ignores:** Generic tables like "قانون", "all_laws", "main_laws"

---

### `_index_law_table(self, table_name: str, conn)`
**What it does:** Extracts metadata from a single law table.

**For each table, collects:**
- All unique categories
- Article count
- Column names
- Subject keywords from titles (words > 3 chars)

**Example output:**
```python
self.law_metadata["قانون العمل"] = {
    "name": "قانون العمل",
    "categories": ["حقوق العمال", "الأجور", "الإجازات"],
    "article_count": 257,
    "columns": ["id", "law_name", "titel", "details", ...]
}
```

---

### `_build_category_index(self)`
**What it does:** Creates reverse mapping from categories to law names.

**Result:**
```python
self.all_categories = {
    "حقوق العمال": ["قانون العمل"],
    "العقود": ["القانون المدني", "قانون التجارة"],
    ...
}
```

---

### `get_all_laws(self) → List[Dict]`
**What it does:** Returns list of all laws with basic metadata.

**Used by:** `/laws` API endpoint for law browsing.

**Returns:**
```python
[
    {"name": "قانون العمل", "article_count": 257, "categories": [...]},
    {"name": "قانون العقوبات", "article_count": 395, "categories": [...]},
    ...
]
```

---

### `get_all_categories(self) → Dict`
**What it does:** Returns all categories with their laws.

**Returns:**
```python
{
    "categories": [
        {"name": "حقوق العمال", "laws": ["قانون العمل"], "count": 1},
        ...
    ],
    "total_categories": 25,
    "total_laws": 50
}
```

---

### `find_laws_by_category(self, category: str) → List[str]`
**What it does:** Finds all laws that belong to a specific category.

**Supports:**
- Exact match: "حقوق العمال"
- Partial match: "العمال" matches "حقوق العمال"

---

### `get_law_info(self, law_name: str) → Optional[Dict]`
**What it does:** Returns detailed metadata for a specific law.

**Supports:**
- Exact name match
- Partial name match (e.g., "العمل" finds "قانون العمل")

---

### `_check_refresh(self)`
**What it does:** Checks if knowledge cache needs refreshing.

**Logic:**
- If never refreshed → Refresh now
- If older than `cache_refresh_minutes` → Refresh now
- Otherwise → Use cached data

---

# Summary Table

| Agent | Primary Role | Key Methods |
|-------|--------------|-------------|
| **Router** | Query Understanding | `classify_query()`, `infer_target_tables()`, `reformulate_query()` |
| **Retrieval** | Database Search | `retrieve()`, `_keyword_search()`, `_normalize_arabic_simple()` |
| **Answer** | Response Generation | `generate_answer()`, `verify_retrieved_articles()`, `analyze_document()` |
| **Knowledge** | Law Indexing | `refresh_knowledge()`, `get_all_categories()`, `find_laws_by_category()` |

---

# Agent Interaction Flow

```
User Query
    │
    ▼
[ROUTER AGENT]
    │ Classify & Route
    ▼
[RETRIEVAL AGENT]
    │ Search Database
    ▼
[ANSWER AGENT]
    │ Generate Response
    ▼
User Response

[KNOWLEDGE AGENT] ──── Provides indexing and caching support
```

---

*Document Version: 1.0*  
*Last Updated: December 2024*  
*Project: Mohamy Legal Assistant*
