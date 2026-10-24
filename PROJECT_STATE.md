# PROJECT_STATE.md

## Current Status (End of Day: 2026-10-21)
**Status:** STABLE. The app is fully functional.
**Last Commit:** `feat: final UI polish - clean SQL data tables and collapsible queries` (or whichever was the last one).

## What We Just Finished (Phase 5)
- **True AI Architecture:** We removed all hardcoded Python regex. The LLM now reads the database schema and the current date to generate SQL dynamically.
- **Dynamic Dates:** The LLM knows today's date, so "yesterday" works perfectly.
- **Dynamic Pricing:** The LLM calculates price as `SUM(total_amount) / SUM(total_qty)`.
- **Fuzzy Matching:** The LLM uses `ILIKE '%item%'` for product names.
- **UI Citations:** The Citation Modal now shows a beautiful data table FIRST, and a collapsible "Show SQL Query" section SECOND.
- **Gmail Automation:** The script `scripts/gmail_sync_ingest.py` is working. Windows Task Scheduler is configured to run it at 7:00 AM daily.

## The Golden Test Suite (These MUST always work)
1. "what is total sales yesterday" -> Returns exact revenue (e.g., 95.12).
2. "what is the price of Marlboro" -> Uses ILIKE, calculates average price.
3. "what is the price of water" -> Returns "Item not found" cleanly.
4. "how many sandwiches sold this month" -> Correct date grouping and sum.
5. "what is Ria's commission" -> Sums `comm` column.
6. "what is the refund policy" -> Routes to Vector Search (not SQL).

## Known Limitations
- **Groq Rate Limits:** We hit the free tier limits if we ask too many questions too quickly. If the API times out, wait 60 seconds.
- **Predictive Analytics:** Not built yet. (Next phase).
- **Typo Tolerance:** The app doesn't handle misspellings well (e.g., "sandwitch").

## The Roadmap (What's Next)
- **Option A:** Predictive Analytics (Vector DB + LLM).
- **Option B:** Analytics Dashboard (React + Recharts).
- **Option C:** Evaluation Harness (Golden Dataset + CI pipeline).

## Important Commands
- **Start Backend:** `uvicorn deli_rag.api.app:app --reload` (Run from root folder).
- **Start Frontend:** `cd frontend && npm run dev` (Run from frontend folder).
- **Ingest Gmail:** `python scripts/gmail_sync_ingest.py`
- **Manual Ingest:** `python scripts/sync_and_ingest.py`

## Current Status (End of Day: 2026-10-22)

**Status:** STABLE. App is fully functional.
**Last Commit:** "feat: local Ollama support with automatic Groq fallback"

## What We Just Finished (Phase 6)
- **Local Ollama Integration:** Added `ollama:llama3` as a selectable model in the UI. The backend now supports routing to either Groq (cloud) or Ollama (local) via the `prefer_local` flag.
- **Automatic Fallback:** If Ollama times out (which it often does on CPU), the LLM client automatically falls back to Groq, and the user gets an answer.
- **UI Model Selection:** The dropdown now fetches available models dynamically from the `/models` endpoint, which now includes Ollama.
- **Backend Schema:** `AskRequest` now accepts a `model` field, and `LLMEntry`/`LLMCfg` schemas support the `ollama` block and `base_url`.

## Tested and Working
1. `what is total sales` -> Correctly returns total via Groq (or Ollama if fast enough).
2. `what is total sales for last week` -> Returns correct value (e.g., $2,327.95).
3. `what is total sales for this month` -> Returns correct value (e.g., $4,550.07).
4. `what is total Ria's commission for this month` -> Returns $75.54.
5. `what is the price of Marlboro` -> Returns price using ILIKE.
6. `what is the refund policy` -> Routes to Vector Search.

## Known Limitations
- **Ollama Speed:** Local Llama 3 is very slow on CPU (6+ minutes for a typical query). To use Ollama effectively, try `phi3` or `mistral` which are much faster. Alternatively, rely on Groq and use Ollama only as a fallback when Groq is rate-limited.
- **Groq Rate Limits:** You still have strict limits on the Free Tier. If you hit them, wait 60 seconds.
- **Predictive Analytics:** Not built yet.
- **Dashboard:** Not built yet.

## The Roadmap (What's Next)
- **Option A:** Predictive Analytics (Vector DB + LLM for forecasting).
- **Option B:** Analytics Dashboard (React + Recharts for visual charts).
- **Option C:** Evaluation Harness (Automated 20-question test).
- **Option D:** Windows Task Scheduler (Finalize the daily Gmail sync).

## Important Commands
- **Start Backend:** `uvicorn deli_rag.api.app:app --reload --port 8000`
- **Start Frontend:** `cd frontend && npm run dev`
- **Run Ollama:** `ollama serve` (should be running in the background)
- **List Local Models:** `ollama list`
- **Ingest Gmail:** `python scripts/gmail_sync_ingest.py`