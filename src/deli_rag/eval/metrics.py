from __future__ import annotations

import math

from deli_rag.eval.golden import GoldenItem
from deli_rag.retrieval.types import ScoredChunk


def is_relevant(chunk: ScoredChunk, item: GoldenItem) -> bool:
    if not item.expected_substrings:
        return False
    hay = (chunk.text + " " + (chunk.context_line or "")).lower()
    return any(s.lower() in hay for s in item.expected_substrings)


def recall_at_k(chunks: list[ScoredChunk], item: GoldenItem, k: int) -> float:
    if not item.expected_substrings:
        return 0.0
    topk = chunks[:k]
    for sub in item.expected_substrings:
        if any(sub.lower() in (c.text + " " + (c.context_line or "")).lower() for c in topk):
            return 1.0
    return 0.0


def reciprocal_rank(chunks: list[ScoredChunk], item: GoldenItem) -> float:
    for rank, c in enumerate(chunks, start=1):
        if is_relevant(c, item):
            return 1.0 / rank
    return 0.0


def ndcg_at_k(chunks: list[ScoredChunk], item: GoldenItem, k: int) -> float:
    dcg = 0.0
    for rank, c in enumerate(chunks[:k], start=1):
        rel = 1.0 if is_relevant(c, item) else 0.0
        dcg += rel / math.log2(rank + 1)
    n_rel = min(len(item.expected_substrings), k)
    idcg = sum(1.0 / math.log2(r + 1) for r in range(1, n_rel + 1))
    return dcg / idcg if idcg > 0 else 0.0