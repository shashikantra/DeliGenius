# DECISIONS.md

Status: Phase 1 in progress. Commit #1 done.
Legend: CONFIRMED = stated by you. PROPOSED = my default, needs your approval. OPEN = unanswered.

## 1. Requirements (from you)

| Topic | Decision | Status |
|---|---|---|
| File types | PDF, DOCX, CSV, XLSX | CONFIRMED |
| PDF quality | Mostly digital, English only | CONFIRMED |
| Volume | 5-10 documents/day, about 10 pages each (about 50-100 pages/day, about 20-35k pages/year) | CONFIRMED |
| Deployment | Local laptop and Docker Compose on one server now, cloud later | CONFIRMED |
| GPU | None, so everything local must run on CPU | CONFIRMED |
| Cloud LLM | Sending questions and retrieved chunks to Groq is acceptable | CONFIRMED |
| PII / retention / audit | No requirements for now. Keep audit log and PII redaction in logs as cheap defaults | CONFIRMED |
| Access control | Seeded demo users (public, internal, confidential, plus groups/tenants). No real login in v1 | CONFIRMED |
| Document intake | Gmail attachments or a local folder | CONFIRMED |
| UI | React frontend over FastAPI | CONFIRMED |
| Model selection | Both: user picks per chat, plus automatic fallback on error/rate limit | CONFIRMED |

## 2. Assumptions I made (change any of them)

| Topic | Assumption | Status |
|---|---|---|
| Concurrency | At most 5 simultaneous users | PROPOSED |
| Latency | Time to first token <= 3 s p50. Total answer <= 10 s p50, <= 20 s p95 including one retry loop | PROPOSED |
| Eval data | Synthetic golden set from sample docs now, replaced/extended by 20-30 real questions later | PROPOSED |
| Scale impact | 100 pages/day is tiny: one Postgres instance, no sharding, brute-force or HNSW pgvector both fine | PROPOSED |

## 3. Stack

| Layer | Choice | Status |
|---|---|---|
| Language / API | Python 3.11+, FastAPI, SSE streaming | PROPOSED |
| Frontend | React (Vite + TypeScript) | CONFIRMED |
| Orchestration | LangGraph for the agent loop. LangChain only for model clients. Not `RetrievalQA` | PROPOSED |
| Store | Postgres + pgvector, own schema via SQLAlchemy/psycopg. Not `langchain_postgres.PGVector` | CONFIRMED |
| Keyword search | Postgres `tsvector` + GIN behind a `KeywordIndex` interface | CONFIRMED |
| Embedder | `bge-small-en-v1.5` (384-dim, 512 tokens, English) | CONFIRMED |
| Reranker | CPU cross-encoder (`bge-reranker-base`) | PROPOSED |
| LLMs (Groq) | Default `openai/gpt-oss-20b`, fallback 1 `openai/gpt-oss-120b` | CONFIRMED |
| Model roles | Fast model for rewrite/classify/route, user-selected model for generation, judge model for validation | PROPOSED |
| Config | Versioned YAML (models, top-k, thresholds, budgets, feature flags) | CONFIRMED |
| Secrets | `.env` via python-dotenv | CONFIRMED |

### Parsers

| Format | Parser | Notes |
|---|---|---|
| PDF | PyMuPDF (text blocks, headings by font size, table detection, page numbers) | Tesseract/RapidOCR fallback for scanned pages |
| DOCX | `python-docx` | Keeps heading styles and tables |
| XLSX | `openpyxl` | One table chunk group per sheet region, header row repeated |
| CSV | `pandas`/`csv` | Row-group chunks with header repeated, plus a table summary |

## 4. Document intake

- A `DocumentSource` interface with two implementations: `LocalFolderSource` (watched `inbox/` folder) and `GmailSource`.
- Phase 1 ships `LocalFolderSource`. `GmailSource` follows once ingestion is stable.
- Gmail design: read-only OAuth scope (`gmail.readonly`), label or allow-listed sender filter, daily scheduled poll plus manual "Sync now", dedup by message ID + attachment `content_hash`, email fields stored as metadata, OAuth tokens kept outside the repo.
- Same logical document arriving in updated form: new hash creates a new `doc_version` and marks the old one superseded.
- Attachments from email are untrusted input. Parse with size limits and no macro execution.

## 5. Structured data (CSV/XLSX)

Questions like "total for March" or "how many rows where X" are unreliable with chunk retrieval. CSV/XLSX tables are loaded into Postgres tables and exposed through the read-only, allow-listed SQL route in Phase 3.

## 6. Model selection and fallback

- UI dropdown populated from `/models`, validated against Groq's live model list at startup.
- The user's pick is tried first. On 429, 5xx or timeout, retry with backoff once, then walk the configured fallback chain.
- UI always shows which model actually answered, and a notice when a fallback was used.

## 7. Open items

1. Approve or change: LangGraph instead of `RetrievalQA`, own schema instead of `PGVector`, `tsvector` first, new parser set. — RESOLVED in §9.
2. Embedder: `bge-small-en-v1.5` (recommended) or MiniLM. — RESOLVED: bge-small.
3. Latency and concurrency assumptions in section 2. — still PROPOSED.
4. Gmail details: personal or Workspace account, and label/sender pattern. — deferred to Phase 1.5.
5. Default access level for emailed documents. — PROPOSED: internal.
6. SQL route for CSV/XLSX: yes or no. — RESOLVED: yes (§9).
7. Confirm Qwen model ID and whether image input is needed. — Qwen gated by runtime validator.
8. Eval data: 20-30 real questions with expected source docs. — still OPEN.

## 8. Phase 1 plan

1. Repo skeleton, config loader, Pydantic schemas, Docker Compose (Postgres + pgvector).
2. DB schema: `documents`, `chunks` (parent/child), `embeddings` (versioned by model), ACL fields, `audit_log`.
3. Parsers for the four formats, with unit tests on sample files.
4. Structure-aware chunker (token limits, overlap, table + caption kept together, context line prefix, parent-child).
5. Metadata assignment, content-hash dedup, versioning, tombstones.
6. Indexer: dense vectors and `tsvector`, incremental updates.
7. `LocalFolderSource` plus an ingest CLI. A small upload endpoint comes with the UI later.
8. Review stop: show sample chunks and metadata for each file type before moving to Phase 2.

## 9. Phase 1 scope resolution (LOCKED — 2026-10-15)

| Topic | Decision | Status |
|---|---|---|
| Product scope | **(C) Both** — RAG agent for PDFs (RIA, lottery, reports) + SQL/analytics track for sales & inventory CSVs | CONFIRMED |
| Vector store | **Own schema** via SQLAlchemy/psycopg (not `langchain_postgres.PGVector`) | CONFIRMED |
| Embedder | **`bge-small-en-v1.5`** (384-dim, 512 tokens) — supersedes MiniLM in the .txt brief | CONFIRMED |
| LangChain role | **Groq client only**; LangGraph for the agent loop | CONFIRMED |
| Orchestration | **LangGraph** | CONFIRMED |
| Keyword search | Postgres `tsvector` + GIN behind `KeywordIndex` interface | CONFIRMED |
| Reranker | CPU cross-encoder `bge-reranker-base` (Phase 2) | CONFIRMED |
| RIA PDFs | **RAG documents** via dedicated `RiaParser` | CONFIRMED |
| NJ Lottery | **Placeholder** — parser stub only | CONFIRMED |
| SQL route for CSV/XLSX | **Yes** — Track 2 in Phase 1 | CONFIRMED |
| Default ACL for emailed docs | **`internal`** | PROPOSED |
| Golden set v1 | **Synthetic** from sample files | PROPOSED |
| Gmail | Deferred to Phase 1.5; `LocalFolderSource` ships in Phase 1 | CONFIRMED |
| Qwen model ID | Unverified; startup validator (`deli-rag models`) gates it | CONFIRMED |

## 10. Local dev DB port (LOCKED — 2026-10-15)

Host has native Postgres 13 and 15 (Windows services `postgresql-x64-13`,
`postgresql-x64-15`) occupying default ports 5432/5433. The pgvector Docker
container publishes on **host port 5434** to avoid shadowing.

- Compose: `ports: ["5434:5432"]`
- Env:     `DATABASE_URL=postgresql+psycopg://deli:sheetal123@localhost:5434/deli_rag`
- Container user/password/db: `deli` / `sheetal123` / `deli_rag`

Any new dev machine must either not have native Postgres on 5433/5434, or
adjust the container's host port in `docker-compose.yml` and `.env` in lockstep.

### 10.1 Commit log

| Commit | Contents | Status |
|---|---|---|
| #1 | Repo skeleton, config loader, Pydantic schemas, DB schema, migration, Groq validator, CLI stubs | **DONE** 2026-10-15 |
| #2 | Parsers (PDF/DOCX/XLSX/CSV), RiaParser, LotteryParser stub, fixtures, tests, `deli-rag inspect` | next |
| #3 | Chunker + metadata + dedup/versioning | pending |
| #4 | Indexer (pgvector + tsvector, incremental) | pending |
| #5 | `LocalFolderSource` + `deli-rag ingest` | pending |
| #6 | Track 2: `sales_daily`, `inventory_snapshot` loaders | pending |
| #7 | Phase 1 review doc | pending |

### 10.4 Deferred to Phase 3

- `inventory_snapshot` loader returns 0 rows — the `loaders.py` `_rowcount` fix
  and CSV `csv_table` routing need a second pass. Will be resolved when the SQL
  route in Phase 3 first consumes this table.
- `fitz` deprecation warning printed on every CLI command — cosmetic; will fix
  when `pdf_parser.py` is next touched.

### 10.5 Commit log (updated)

| Commit | Contents | Status |
|---|---|---|
| #1 | Repo skeleton, config, schemas, DB, migration, Groq validator | DONE 2026-10-15 |
| #2 | Parsers (7 formats), fixtures, tests, `inspect` CLI | DONE 2026-10-15 |
| #3 | Chunker, metadata, dedup, writer, Track-2 loaders | DONE 2026-10-15 |
| #4 | Embedder (bge-small), indexer, `index` CLI | DONE 2026-10-16 |
| #5 | Hybrid retrieval (dense + keyword + RRF), ACL pre-filters, `query` CLI | DONE 2026-10-16 |
| #6 | Reranker (bge-reranker-base, optional), eval harness + golden set, `eval` CLI | DONE 2026-10-16 |
| #7 | Query understanding, transformation, routing, Groq generation, validation | Phase 3 |

### 10.9 Phase 4 progress (end of day 2026-10-16)

- **Message A (compression)** — DONE. `compress.py` strips duplicate chunks
  by content hash, drops below score floor, merges adjacent same-section chunks,
  enforces token budget. Runs in pipeline after retrieval.
- **Message B (agent loop)** — DONE. `agent.py` wraps `Asker` with a
  sufficiency-check retry loop. Config-driven budgets. Verified end-to-end:
  RIA commission question → 1 iteration, 4 dedup'd chunks (from 8), answer `216.56`.
  Ambiguous question → abstains on iteration 1 with clarification prompt.
- **Message C (FastAPI + SSE)** — NOT STARTED. Files listed in my last message.
  Prerequisites: add `fastapi`, `uvicorn[standard]`, `sse-starlette` to
  `pyproject.toml` and `pip install -e ".[dev]"`. Then create five files under
  `src/deli_rag/api/` and one test file `tests/test_api.py`.

## 11. Query Logic & Data Cleaning Rules (LOCKED 2026-10-18)

### 11.1 Query Logic (The Mental Model)

Before writing any SQL or LLM prompt rules, we established the following mental model for the agent:

1. **Inventory Defaults:** 
   - If no date is specified, the agent defaults to the **most recent date** available in the database.
   - If no specific category/variant is specified (e.g., "Marlboro"), it returns the **aggregate sum** of all matching variants.
   - If a specific category is specified (e.g., "Marlboro Menthol"), it filters strictly. If the match is fuzzy, it asks the user to clarify.

2. **Null Handling:**
   - During ingestion, any `NULL` or empty `in_stock` value in the CSV will be coerced to `0`.
   - The LLM should never see a `NULL` in the SQL output for critical numeric fields.

3. **LLM Responsibility vs. SQL Responsibility:**
   - **SQL:** Does the filtering, summing, and grouping. The LLM is *not* responsible for math.
   - **LLM:** Takes the pre-aggregated SQL results and formats them into a human-readable sentence.

4. **Non-Regression Rule:**
   - Any change to `router.py` or `sql_route.py` must be accompanied by a unit test covering the specific edge case (e.g., no date, specific category, null handling).

### 11.2 Data Cleaning Rules (Ingestion)

These rules apply to all structured data during the ingestion phase (`loaders.py`), *before* it touches PostgreSQL.

**Inventory CSVs (`Inventory_Status_*.csv`):**
- **Missing `In Stock`:** Default to `0`.
- **Missing `Department`:** Fill with `"General"`.
- **Missing UPC:** Drop the row and log to `audit_log` (action: `ingest_error`).
- **Duplicate UPCs:** Sum the `In Stock` quantities.
- **Whitespace:** Trim all strings.
- **Casing:** Convert product names to Title Case (e.g., "Marlboro Red Filter").
- **Numeric Strings:** Strip `$` and `,`, convert to `float` or `int`.

**Sales History CSVs (`Sales_History_*.csv`):**
- **Missing UPC (Category Row):** Keep as `kind='category'`. Do not drop.
- **Negative Quantities:** Classify as `kind='refund'`. Do not take `ABS()`.
- **Numeric Strings:** Strip `$` and `,`, convert to `float` or `int`.

**RIA PDFs (`AgentBalanceReport.pdf`):**
- **Currency Symbols:** Strip `$` and `,`.
- **Dates:** Convert `MM/DD/YYYY` to ISO `YYYY-MM-DD` (UTC).

**General (All Formats):**
- **Timestamps:** All `ingested_at` must be UTC.
- **Bad Rows:** Do not abort the file. Drop the row and log the reason + raw data to `audit_log`.
- 
Current test count: **100 passed, 2 skipped**.

## 12. Phase 4.5: Pipeline Stabilization & Text-to-SQL (LOCKED 2026-10-20)

### 12.1 Ingestion Fixes
- **Parser Routing:** Fixed `base.py` `get_parser_for` logic (parentheses bug) so `AgentBalanceReport.pdf` correctly routes to `RiaParser`, not `CsvParser`.
- **OCR Fallback:** Installed Tesseract v5.5.3. Updated `pdf_parser.py` to explicitly point to `C:\Program Files\Tesseract-OCR\tesseract.exe`. Scanned PDFs now extract text and tables successfully.
- **NUL Bytes:** Added Pydantic `field_validator` to `base.py` to strip `\x00` (NUL) bytes from `ParsedElement`, `TableRecord`, and `ParsedDocument`. This prevents PostgreSQL `DataError` crashes on RIA PDFs.
- **RIA Table Extraction:** Updated `RiaParser._classify_table` to normalize headers (stripping punctuation/case) so OCR output (`Ref. No`) matches the expected `ref no`.
- **Markdown Tables:** Updated `CsvParser` to emit Markdown-formatted tables (`|---|---|`) instead of raw pipes, enabling UI table rendering.

### 12.2 Architecture Shift: Dynamic Text-to-SQL
- **Deprecated:** The hardcoded `_SQL_SIGNALS` regex list in `router.py` and the static `SqlRoute` handlers (e.g., `_handle_total_sales`). This approach did not scale.
- **New Approach:** Implemented `TextToSql` agent (`src/deli_rag/agent/text_to_sql.py`).
  - It dynamically inspects the PostgreSQL schema (`sales_daily`, `ria_transactions`, etc.).
  - It passes the schema to `gpt-oss-120b` (configured via the `sql` role in `base.yaml`).
  - The LLM generates a safe `SELECT` query, which is executed and returned as `SqlEvidence`.
  - This scales to any analytical question (e.g., "top 5 selling", "RIA commission", "out of stock") without code changes.
- **Router Simplification:** `router.py` now simply routes `fact`, `comparison`, and `summary` intents directly to `sql`, bypassing vector search to save tokens and latency.
- **Bypassed Transformation:** In `pipeline.py`, queries with `< 8` words and no history skip the `transform()` LLM call entirely.
- **Bypassed Validation:** In `ask.py`, the `validate()` LLM call is bypassed to save API limits, reducing the total LLM calls per request to exactly 2 (SQL generation + Answer generation).

### 12.3 Frontend Enhancements
- **API URLs:** Replaced hardcoded `http://localhost:8000` with `import.meta.env.VITE_API_URL || '/api'` in `Chat.tsx`.
- **Citation Tables:** Updated the Citation Modal in `Chat.tsx` to parse Markdown table strings and render native HTML tables for CSV evidence.

## 13. Phase 5: Final AI Architecture & Production Polish (LOCKED 2026-10-21)

### 13.1 The "True AI" Agent Architecture
We pivoted away from hardcoded Python regex (which broke easily) to a pure LLM-driven approach.

- **The Router (`router.py`):** Python no longer guesses what is SQL vs. Documents. It relies solely on the `intent` classification from the LLM (via `understanding.py`). 
  - `fact`, `comparison`, `summary` → SQL Route.
  - `policy`, `troubleshooting` → Vector Search.
- **The Text-to-SQL Engine (`text_to_sql.py`):**
  - The LLM is given the database schema and the **current date**.
  - It dynamically calculates "yesterday" or "this month" without hardcoded Python regex.
  - It is instructed to use `name ILIKE '%item%'` for fuzzy matching (e.g., matching "Marlboro" to "Marlboro Red Filter").
  - It calculates unit price as `ROUND(SUM(total_amount) / NULLIF(SUM(total_qty), 0), 2)`.
- **The Fallback:** If the SQL query returns 0 rows, the LLM gracefully says "Item not found" rather than crashing or hallucinating.

### 13.2 UI Citation Fix (Data Visibility)
We fixed the black-box nature of the AI. When a user clicks a SQL citation in the UI, they now see:
1. **A clean HTML Data Table** containing the exact result rows returned by the database.
2. **A collapsible "Show SQL Query" section** for developers to verify the LLM's generated SQL.
3. **A summary** of the row count.

### 13.3 Gmail Automation
- Created `scripts/gmail_sync_ingest.py`.
- It connects to Gmail via OAuth (`credentials.json` / `token.json`).
- It recursively searches email payloads for attachments.
- It appends dates to filenames (e.g., `AgentBalanceReport_20261020.pdf`) to prevent overwriting.
- It hands off the downloaded files to `sync_and_ingest.py` for parsing, OCR, chunking, and SQL loading.
- **Deployment:** Windows Task Scheduler is set up to run this script daily at 7:00 AM.

### 13.4 Known Limitations (Deferred to Phase 6)
- **Groq Rate Limits:** The Free Tier for `gpt-oss-120b` limits requests per minute. If a user asks too many complex questions, the app may timeout. (Mitigated by reducing LLM calls and adding a 2s sleep).
- **Predictive Analytics:** The app can currently answer "what happened" and "what is happening" but cannot yet predict "what will happen" (e.g., "Predict sales for next Friday"). This requires building a `predictor.py` using Vector DB trend chunks.
- **Typo Tolerance:** If the LLM searches for `%sandwitch%`, it will return 0 rows because the database says "Sandwich". (Future fix: Enable `pg_trgm` in PostgreSQL for fuzzy spelling matching).

## 14. Test Suite (Golden Questions)
Before adding new features, the following questions must pass using the current architecture:
1. "what is total sales yesterday" → Returns exact revenue.
2. "what is the price of Marlboro" → Uses `ILIKE` and returns average price.
3. "what is the price of water" → Returns "Item not found" cleanly.
4. "how many sandwiches sold this month" → Correct date grouping and sum.
5. "what is Ria's commission" → Sums `comm` column.
6. "what is the refund policy" → Routes to Vector Search.

