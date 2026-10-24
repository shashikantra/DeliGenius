# deli-rag-agent (Phase 1 · Commit #1)

Evidence-first RAG agent for a Deli/Grocery business.
- **Track 1** — PDF/DOCX/XLSX RAG for RIA, lottery, reports
- **Track 2** — SQL/analytics for daily sales & inventory CSVs

## Quickstart

```bash
cp .env.example .env           # then edit GROQ_API_KEY
docker compose up -d           # Postgres 16 + pgvector
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
deli-rag models                # validates Groq model IDs
pytest -q
```

## What ships in Commit #1
- Versioned config loader (`config/base.yaml`)
- Pydantic schemas: `Document`, `Chunk`, `Embedding`, `Filters`, `ACL`
- Postgres schema: `documents`, `chunks` (with `tsv` trigger), `embeddings` (HNSW), `audit_log`
- Groq model-ID validator (gates Qwen until confirmed)
- CLI stubs, tests

## What's next
- **Commit #2** — parsers (PDF/DOCX/XLSX/CSV) + RIA + Lottery stub
- **Commit #3** — chunker + metadata + dedup/versioning
- **Commit #4** — indexer (pgvector + tsvector)
- **Commit #5** — `LocalFolderSource` + `deli-rag ingest`
- **Commit #6** — Track 2: `sales_daily`, `inventory_snapshot` loaders
- **Commit #7** — Phase 1 review doc