# Phase 4 Review — Compression, Agent Loop, FastAPI

**Status: COMPLETE 2026-10-17**

## Delivered

### Message A — Context compression
- `src/deli_rag/agent/compress.py` — dedup by content hash, score floor,
  adjacent-page merge (only for distinct adjacent pages with matching sections),
  total token budget, max chunk cap
- 9 unit tests
- Verified on RIA query: `compress: in=8 out=4 dups=4 tokens=577` (p.1/p.3
  duplicates eliminated before hitting Groq)

### Message B — Agent loop
- `src/deli_rag/agent/sufficiency.py` — heuristic check: sufficient /
  marginal / insufficient based on doc count, SQL presence, best score
- `src/deli_rag/agent/agent.py` — `Agent` class wrapping `Asker` with:
  - Retry on low confidence / abstained / insufficient evidence
  - `broaden_factor` doubling of `k` up to `max_k`
  - `max_iterations` and `latency_budget_s` enforcement
  - Graceful abstain path with reason
  - Full `Attempt` trace on the result
- Config: `AgentCfg` in settings + `agent:` block in `base.yaml`
- 5 unit tests
- Verified: RIA commission → 1 iteration, sufficient; ambiguous query → abstains

### Message C — FastAPI + SSE
- `src/deli_rag/api/app.py` — app factory, CORS for localhost:5173/3000
- `src/deli_rag/api/routes.py` — 5 endpoints:
  - `POST /ask` — JSON RAG with citations
  - `POST /ask/stream` — SSE streaming variant
  - `POST /feedback` — thumbs up/down to `audit_log`
  - `GET /models` — configured Groq models
  - `GET /health` — DB + Groq + embedder readiness
- `src/deli_rag/api/middleware.py` — request ID, access log, error handling
- `src/deli_rag/api/models.py` — Pydantic request/response contracts
- 5 API tests including end-to-end `/ask`
- Verified: `/health` returns `{"status":"ok","db":true,"groq":true,"embedder_loaded":true}`

## Test suite at close

**105 passed, 2 skipped** — full coverage across all phases.

## Known issues (deferred to Phase 5)

- Bare-number answers on RIA commission query ("216.56" instead of a sentence) —
  add rule to `prompt.py` when polishing UI-visible responses.
- `ask.py`'s abstain reason is generic ("no evidence retrieved") vs. the specific
  pipeline reason — surface the trace reason in the UI response.
- No `GET /documents` endpoint yet — Phase 5 needs one for a document browser.

## What Phase 5 will deliver

- Vite + React + TypeScript frontend
- Chat view with SSE streaming from `/ask/stream`
- Citations rendered as clickable chips (source file + page)
- Model picker populated from `/models`
- Feedback buttons wired to `/feedback`
- Health badge from `/health`
- Optional: document browser + ingestion status