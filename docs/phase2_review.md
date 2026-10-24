# Phase 2 Review — Retrieval, Reranking, Eval Harness

**Status: COMPLETE 2026-10-16**

## Delivered

### Embeddings
- `BAAI/bge-small-en-v1.5` (384-dim) via sentence-transformers
- Query prefix `"Represent this sentence for searching relevant passages: "` on
  the query side only (bge-small training contract)
- 43 chunks embedded, versioned as `(model_name, model_version) = (BAAI/bge-small-en-v1.5, v1)`
- `embeddings` table has HNSW cosine index (`ix_embeddings_hnsw`)
- `deli-rag index` idempotent: second run reports `0 / 0 chunks`

### Retrieval
- Dense: pgvector cosine, ACL/tenant/supersession pre-filters inside SQL
- Keyword: Postgres `ts_rank_cd` over `tsv` GIN index, same pre-filters
- Fusion: Reciprocal Rank Fusion (k=60), score fields merged across retrievers
- `HybridRetriever` returns `RetrievalResult` with per-stage candidates counts
- `deli-rag query "..." --k N --acl ...` — retrieval-only CLI

### Reranking (optional)
- `BAAI/bge-reranker-base` cross-encoder via sentence-transformers CrossEncoder
- Enabled by passing `reranker=` to `HybridRetriever` or `--rerank` to `deli-rag eval`
- Config-driven: `config/base.yaml > reranker.min_score` threshold

### Eval harness
- Golden set format (`eval/golden/phase2_v1.yaml`): 12 items, one abstain case
- Metrics: recall@5, MRR, nDCG@5, per-item latency, aggregate
- `deli-rag eval` CLI exits 1 if `recall@5 < 0.5` — CI-gateable
- 45 tests passing (parser, chunker, writer, retrieval, eval, embeddings, fusion)

## Known issues (deferred to Phase 3)

1. **Duplicate chunks in top-k** — RIA PDF has Account Overview on p.1 and p.3, so
   identical text produces two chunks. RRF keeps both. Fix in Phase 3's context
   compression step: dedupe by `content_hash`, keep highest score.
2. **Keyword OR-query tuning** — `plainto_tsquery` requires ALL terms, so
   `"RIA commission"` returns 0 keyword hits (RIA is not a token in the corpus).
   Fix: synonym expansion or `to_tsquery` with `|` in Phase 3's query transformation.
3. **HF unauth warning** — cosmetic; set `HF_TOKEN` in `.env` if rate limits bite.

## What Phase 3 will deliver

1. Query understanding: intent classification, entity extraction, ambiguity detection
2. Query transformation: rewrite, synonym expansion, HyDE, decomposition
3. Routing: SQL route for `sales_daily` / `inventory_snapshot` / `ria_*`; doc route for RAG
4. Generation via Groq: strict JSON schema, numbered evidence blocks, citation IDs
5. Validation: groundedness, citation validity, PII redaction, schema compliance
6. `deli-rag ask "..."` — full pipeline end to end

## What's explicitly NOT in Phase 3

- Agent loop / retry-on-low-confidence (Phase 4)
- Compression + prompt + validation refinement (Phase 4)
- FastAPI layer + React UI (Phase 5)