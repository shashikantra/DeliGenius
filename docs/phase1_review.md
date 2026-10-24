# Phase 1 Review — Ingestion, Chunking, Persistence, Track-2 Loaders

**Status: COMPLETE 2026-10-15**

## Delivered

### Ingestion (parsers)
- `Parser` protocol with `@register` self-registration
- 7 implementations: PdfParser, DocxParser, XlsxParser, CsvParser, SalesCsvParser,
  RiaParser, LotteryParser (stub)
- Longest-suffix dispatch: `.ria.pdf` → Ria, `.sales.csv` → SalesCsv, `.lottery.pdf` → Lottery stub
- Parser output model: `ParsedDocument` with `pages` (element stream) + `tables` (TableRecords)
- Layout-aware PDF: font-size headings, table detection, table caption preservation
- CSV: header auto-detection, title-line skip, footer skip
- RIA: three TableRecords from one PDF (account_overview from paragraphs, branch_summary,
  transactions)
- Real-file fixtures (inventory CSV, sales CSV, RIA PDF) tested alongside synthetic

### Chunking
- Structure-aware: sections split at headings; parent = whole section, child = retrieval unit
- Tables kept whole with caption; `table_summary` populated
- Context line prefixed to each chunk (`<doc_title> — <section>`) under token budget
- Packing: adjacent paragraphs merged until `child_target_tokens`
- Oversized paragraphs split at sentence boundaries
- Token counting behind `TokenCounter` protocol (heuristic now, real BPE in Phase 2)
- Config-driven: all limits from `config/base.yaml`

### Persistence
- `documents` + `chunks` tables (migration 0001_initial) with tsv GIN index + trigger
- Transactional writer with dedup by content_hash
- Doc versioning: same logical doc_id (date suffix stripped) + different hash = new version;
  old marked `superseded_by`
- Identical re-upload → `skip_identical`, no rows written
- ACL + tenant + groups propagated from Document to every Chunk
- `audit_log` entry per ingest

### Track-2 (structured data)
- 4 tables via migration 0002_track2_tables: `sales_daily`, `inventory_snapshot`,
  `ria_daily_summary`, `ria_transactions`
- All idempotent via `(source_file, row_hash)` unique constraint
- `StructuredLoader` routes TableRecords by name and CSV by column shape

### CLI
- `deli-rag inspect <file>` — parse + dump parsed structure as JSON
- `deli-rag load <file>` — parse + write TableRecords to Track-2 tables
- `deli-rag models` — validate Groq model IDs against live endpoint

### Tests
- 30 passing (parsers, chunker, metadata, dedup, writer, structured loaders)
- 1 skipped (integration test guarded by fixture presence)
- Real fixtures validated end-to-end

## Known issues (deferred)

- `inventory_snapshot` currently loads 0 rows — `loaders.py` `_rowcount` fix pending.
  Does not block Phase 2. Will be resolved in Phase 3 when the SQL route first
  consumes the table.
- `fitz` deprecation warning printed on each command — cosmetic, will fix when touched.

## Locked decisions (see DECISIONS.md §9, §10)

- Own Postgres schema (not langchain_postgres.PGVector)
- Embedder: `bge-small-en-v1.5` (chosen in Phase 2)
- LangChain only for Groq client; LangGraph for orchestration
- Postgres tsvector + GIN for keyword search
- Container DB on host port 5434 (native Postgres 13/15 on 5432/5433)

## What Phase 2 will deliver

1. Embedder implementation (`bge-small-en-v1.5` via sentence-transformers)
2. Indexing pipeline: chunk → embedding → `embeddings` table (versioned by model)
3. Hybrid retrieval: pgvector dense + tsvector keyword, fused with Reciprocal Rank Fusion
4. Pre-filters inside retrievers: ACL, tenant, groups, doc_type, freshness
5. Cross-encoder reranker (`bge-reranker-base`) with score threshold
6. Golden-set eval harness: recall@k, MRR, nDCG, latency, cost
7. CI gate: fail on metric regression

## What's explicitly NOT in Phase 2

- Query understanding / transformation (Phase 3)
- SQL routing / analytics queries (Phase 3)
- Prompt construction / generation / validation (Phase 4)
- Agent loop / API / UI (Phase 5)