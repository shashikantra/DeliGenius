from __future__ import annotations

from sqlalchemy.orm import Session

from deli_rag.config.settings import get_config
from deli_rag.embeddings.base import Embedder
from deli_rag.reranking.base import Reranker
from deli_rag.retrieval.dense import DenseRetriever
from deli_rag.retrieval.fusion import reciprocal_rank_fusion
from deli_rag.retrieval.keyword import KeywordRetriever
from deli_rag.retrieval.types import RetrievalResult
from deli_rag.schemas import Filters


class HybridRetriever:
    """Dense + keyword retrieval, fused with RRF, optionally reranked.

    ACL / tenant filters are SQL WHERE clauses inside each retriever —
    no disallowed chunk ever leaves the database."""

    def __init__(
        self,
        session: Session,
        embedder: Embedder,
        reranker: Reranker | None = None,
    ) -> None:
        self.session = session
        self.cfg = get_config().retrieval
        self.dense = DenseRetriever(session, embedder)
        self.keyword = KeywordRetriever(session)
        self.reranker = reranker

    def search(
        self, query: str, *, filters: Filters, k: int | None = None,
    ) -> RetrievalResult:
        k = k or self.cfg.final_top_k

        dense_hits = self.dense.search(query, k=self.cfg.dense_top_k, filters=filters)
        keyword_hits = self.keyword.search(query, k=self.cfg.keyword_top_k, filters=filters)

        fused = reciprocal_rank_fusion(dense_hits, keyword_hits, k=self.cfg.rrf_k)

        if self.reranker and fused:
            top_in = self.cfg.final_top_k * 3   # keep more than we'll return
            candidates = fused[:top_in]
            scores = self.reranker.score(query, [c.text for c in candidates])
            for c, s in zip(candidates, scores):
                c.rerank_score = s
            kept = [c for c in candidates
                    if c.rerank_score is None
                    or c.rerank_score >= get_config().reranker.min_score]
            kept.sort(key=lambda c: c.rerank_score or 0.0, reverse=True)
            fused = kept

        fused = fused[:k]

        return RetrievalResult(
            query=query,
            chunks=fused,
            dense_candidates=len(dense_hits),
            keyword_candidates=len(keyword_hits),
            fused_candidates=len(fused),
        )