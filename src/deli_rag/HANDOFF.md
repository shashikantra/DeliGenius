# DeliGenius RAG Agent — Handoff Document

## Project Root
`C:\Shashi\MyProjects\DeliGenius`

## Current Status (as of 2026-10-23)
**STABLE.** The app is fully functional. All tests pass. Last commit is clean.

## Tech Stack
- **Backend:** Python 3.12, FastAPI, SQLAlchemy, PostgreSQL + pgvector, port 8000
- **Frontend:** React + Vite + TypeScript, port 5173
- **Embeddings:** BAAI/bge-small-en-v1.5 (384-dim, CPU)
- **LLMs:** 
  - Primary: `openai/gpt-oss-20b` (Groq)
  - Fallback: `openai/gpt-oss-120b` (Groq)
  - Local: `ollama:llama3` (slow on CPU, used as fallback only)
- **Search:** Hybrid (dense pgvector + BM25 tsvector) with RRF fusion
- **Reranker:** bge-reranker-base (CPU)
- **Ingestion:** Local folder + Gmail (OAuth) + Tesseract OCR for scanned PDFs

## What Works (Tested and Verified)
1. **Data Ingestion:**
   - CSV (Sales/Inventory) → parsed → `sales_daily`, `inventory_snapshot` tables
   - PDF (RIA Agent Balance Report) → OCR → `ria_transactions`, `ria_daily_summary` tables
   - Gmail auto-sync: `python scripts/gmail_sync_ingest.py`
   - Windows Task Scheduler configured for 7:00 AM daily

2. **AI Text-to-SQL (Dynamic, No Hardcoding):**
   - User asks a question in natural language
   - Router classifies as SQL or Document (keyword-based)
   - `text_to_sql.py` uses Few-Shot prompt + schema + today's date → LLM generates SQL
   - Backend executes SQL → returns actual data value
   - **Bypass:** `ask.py` returns SQL results directly (no second LLM call)
   - If SQL returns 0 rows, fallback suggests similar items

3. **Verified Query Examples:**
   - "what is total sales for last week" → $2,327.95
   - "what is total RIA commission this month" → 75.54
   - "what is the price of Marlboro" → 16.50 (via ILIKE '%marlboro%')
   - "what is the latest date we have for sales data" → 2026-10-20

4. **UI Features:**
   - Chat interface with citations
   - Citation modal shows:
     - Data table (actual rows)
     - Collapsible "Show SQL Query" (the generated SQL)
     - Summary
   - Model dropdown (Groq + Ollama)
   - Feedback thumbs up/down → `audit_log`

5. **Document RAG:**
   - Policy/FAQ questions route to Vector Search
   - RIA PDF text searchable via semantic search

## Known Limitations
- **Groq Rate Limits:** Free Tier allows ~10-15 requests/min. If exceeded, wait 60 seconds.
- **Ollama is Slow:** llama3 on CPU takes 6+ minutes for SQL. Use `phi3` for faster local responses, or rely on Groq.
- **No Predictive Analytics:** Cannot forecast future sales yet.
- **No Dashboard:** No charts, only text answers.
- **No Eval Harness:** No automated regression tests.
- **Typos:** "sandwitch" won't match "sandwich" (could use `pg_trgm` extension).

## Critical Files (Do NOT break these)
| File | Purpose |
|---|---|
| `src/deli_rag/agent/text_to_sql.py` | LLM → SQL generation (Few-Shot prompt) |
| `src/deli_rag/agent/ask.py` | Orchestrator: pipeline → bypass → LLM → answer |
| `src/deli_rag/agent/llm.py` | Groq + Ollama client with fallback |
| `src/deli_rag/agent/router.py` | SQL vs. doc routing |
| `src/deli_rag/agent/prompt.py` | Final answer LLM prompt (formatting) |
| `src/deli_rag/api/routes.py` | FastAPI endpoints (`/ask`, `/models`, `/chunks`) |
| `src/deli_rag/api/models.py` | Pydantic schemas (`AskRequest` has `model` field) |
| `src/deli_rag/config/settings.py` | Pydantic config schemas |
| `config/base.yaml` | Versioned config (LLMs, embedder, chunking) |
| `frontend/src/components/Chat.tsx` | React UI (dropdown, modal, citations) |
| `src/deli_rag/agent/sql_route.py` | `SqlEvidence` dataclass |

## How to Start the App
**Terminal 1 (Backend):**
```powershell
cd C:\Shashi\MyProjects\DeliGenius
uvicorn deli_rag.api.app:app --reload --port 8000