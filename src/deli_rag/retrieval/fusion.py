from __future__ import annotations

from deli_rag.retrieval.types import ScoredChunk


def reciprocal_rank_fusion(
    *ranked_lists: list[ScoredChunk],
    k: int = 60,
) -> list[ScoredChunk]:
    """Reciprocal Rank Fusion across N ranked lists.

    score(chunk) = sum over lists of 1 / (k + rank_in_list)

    Metadata from every list is merged: whichever retriever first saw a chunk
    provides the base record, and score fields from later lists are merged in
    (so a keyword-only or dense-only match still shows its own score, and a
    both-hits chunk shows both)."""
    scores: dict[str, float] = {}
    merged: dict[str, ScoredChunk] = {}

    for ranked in ranked_lists:
        for rank, chunk in enumerate(ranked, start=1):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank)
            if chunk.chunk_id not in merged:
                merged[chunk.chunk_id] = chunk.model_copy()
            else:
                # Merge score fields from later lists into the existing record.
                existing = merged[chunk.chunk_id]
                if existing.dense_score is None and chunk.dense_score is not None:
                    existing.dense_score = chunk.dense_score
                if existing.keyword_score is None and chunk.keyword_score is not None:
                    existing.keyword_score = chunk.keyword_score
                if existing.rerank_score is None and chunk.rerank_score is not None:
                    existing.rerank_score = chunk.rerank_score

    out: list[ScoredChunk] = []
    for chunk_id, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True):
        c = merged[chunk_id]
        c.rrf_score = score
        out.append(c)
    return out