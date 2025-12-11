# Agentic Legal Assistant - Setup Guide

## Overview
This enhanced version of your legal assistant uses a multi-agent architecture to provide intelligent responses with dataset learning capabilities.

## Architecture

### 🤖 Four Specialized Agents

1. **Router Agent** (`agents/router_agent.py`)
   - Classifies query intent (generic, specific, category browse)
   - Extracts legal concepts from queries
   - Routes to appropriate handler

2. **Knowledge Agent** (`agents/knowledge_agent.py`)
   - Learns entire dataset on startup
   - Maintains index of all laws, categories, subjects
   - Handles generic questions about available laws
   - Suggests relevant categories

3. **Retrieval Agent** (`agents/retrieval_agent.py`)
   - Performs intelligent database search
   - Uses Gemini to understand legal concepts
   - Scores and ranks results by relevance

4. **Answer Agent** (`agents/answer_agent.py`)
   - Generates summaries of retrieved laws
   - Explains complex legal text in simple language
   - Suggests related topics

## Installation

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variable

```bash
# Windows PowerShell
$env:GEMINI_API_KEY="your-api-key-here"

# Windows CMD
set GEMINI_API_KEY=your-api-key-here

# Linux/Mac
export GEMINI_API_KEY=your-api-key-here
```

### 3. Ensure Database Exists

Make sure `law_database.db` is in the same directory as `mohamy.py`.

### 4. Run the Server

```bash
uvicorn mohamy:app --reload --host 0.0.0.0 --port 8000
```

## New Features

### ✨ Intelligent Query Classification

The system now understands different types of questions:

- **Generic Questions**: "ما هي القوانين المتاحة؟"
  - Returns categories and available laws
  
- **Specific Queries**: "ما هي حقوق العامل في الإجازات؟"
  - Performs intelligent retrieval with Gemini
  - Returns relevant articles with AI-generated summary
  
- **Category Browsing**: "أريد رؤية قوانين العمل"
  - Shows laws in specific category

### 📚 Dataset Learning

The Knowledge Agent learns your entire dataset on startup:
- Indexes all law tables
- Extracts categories and subjects
- Maintains statistics (article counts, etc.)
- Refreshes cache every 60 minutes

### 🎯 Enhanced Responses

Every response now includes:
- **AI-generated summary** answering the user's question
- **Relevant articles** from the database
- **Related topics** for further exploration
- **Simplified explanations** for complex legal text

## API Endpoints

### Existing Endpoints (Enhanced)

#### `POST /ask`
Now uses agentic workflow with intelligent routing.

**Request:**
```json
{
  "query": "ما هي حقوق العامل في الإجازات؟"
}
```

**Response:**
```json
{
  "stage": "final_answer",
  "intent": "specific_law_query",
  "summary": "AI-generated summary in Arabic...",
  "laws": [...],
  "related_topics": ["موضوع 1", "موضوع 2"],
  "message": "تم العثور على 10 مادة قانونية ذات صلة:"
}
```

#### `POST /details`
Now includes Gemini-powered explanation.

**Response:**
```json
{
  "stage": "details",
  "law": {
    "id": 123,
    "titel": "...",
    "details": "...",
    "gemini_explanation": "Simplified explanation...",
    "simplified_text": "..."
  }
}
```

### New Endpoints

#### `GET /categories`
Get all available categories with their laws.

**Response:**
```json
{
  "status": "ok",
  "categories": [
    {
      "name": "العمل",
      "laws": ["قانون العمل", "قانون التأمينات"],
      "count": 2
    }
  ],
  "total_categories": 15,
  "total_laws": 8
}
```

#### `GET /laws`
Get all available laws with metadata.

**Response:**
```json
{
  "status": "ok",
  "laws": [
    {
      "name": "قانون العمل",
      "article_count": 245,
      "categories": ["العمل", "الأجور"]
    }
  ],
  "total_laws": 8
}
```

#### `GET /health`
Enhanced health check showing agent status.

## Fallback Mode

If Gemini API is not available or agents fail to initialize:
- System automatically falls back to original keyword-based search
- No errors, just reduced intelligence
- All endpoints still work

## Frontend Integration

Your existing Angular frontend should work without changes! The response format is backward compatible.

### Optional Enhancements

You can enhance your Angular app to use new features:

1. **Show AI Summary**: Display `summary` field prominently
2. **Related Topics**: Show `related_topics` as clickable suggestions
3. **Categories Page**: Use `/categories` endpoint for browsing
4. **Laws List**: Use `/laws` endpoint for overview page
5. **Simplified Explanations**: Show `gemini_explanation` in details view

## Testing

### Test Generic Question
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "ما هي القوانين المتاحة؟"}'
```

### Test Specific Query
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "ما هي حقوق العامل في الإجازات؟"}'
```

### Test Categories
```bash
curl http://localhost:8000/categories
```

### Test Health
```bash
curl http://localhost:8000/health
```

## Performance

- **First Request**: ~3-5 seconds (includes dataset learning)
- **Subsequent Requests**: ~2-3 seconds (with Gemini calls)
- **Fallback Mode**: ~0.5-1 second (keyword search only)

## Troubleshooting

### Agents Not Initializing
- Check `GEMINI_API_KEY` is set correctly
- Check internet connection
- View logs for specific error messages

### Slow Responses
- Normal for first request (dataset learning)
- Consider reducing `TOP_K_RESULTS` in config
- Check Gemini API quota

### Database Errors
- Ensure `law_database.db` exists
- Check table names start with 'قانون'
- Verify database schema matches expected format

## Next Steps

1. Copy all files to your existing project directory
2. Install dependencies
3. Set API key
4. Run the server
5. Test with your Angular frontend
6. Optionally enhance frontend to use new features
