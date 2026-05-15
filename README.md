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

### 2. Set Environment Variables

```bash
# Windows PowerShell
$env:GOOGLE_API_KEY="your-api-key-here"
$env:ALLOWED_ORIGINS="http://localhost:4200,https://yourdomain.example"

# Linux/Mac
export GOOGLE_API_KEY=your-api-key-here
export ALLOWED_ORIGINS="http://localhost:4200,https://yourdomain.example"
```

If `GOOGLE_API_KEY` is unset, the API still boots in **fallback mode** — retrieval works, but LLM-powered answers return canned messages.

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

#### `POST /ask`
Main legal-question endpoint. Body: `{ "query": "...", "session_id": "..." }`.
Returns `{ summary, steps, answer, articles, verification, related_topics, intent, source, ... }`.

#### `POST /upload_document`
Multipart form upload (`file` + optional `session_id`) for OCR/analysis of a legal document image or text.
Returns `{ status, filename, analysis, extracted_text, full_text_length }`.

#### `GET /laws`
Returns categorized index of indexed laws from the Knowledge Agent:
`{ categories: [{name, laws, count}], total_categories, total_laws }`.

#### `GET /health`
`{ status: "ok", llm_enabled, law_tables, indexed_laws }`. Use for container healthchecks.

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
3. **Categories Page**: Use `/laws` endpoint for browsing
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
curl http://localhost:8000/laws
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
- Check `GOOGLE_API_KEY` is set correctly
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
