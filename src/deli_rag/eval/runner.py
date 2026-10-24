from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from deli_rag.embeddings.base import Embedder
from deli_rag.eval.golden import GoldenSet
from deli_rag.eval.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from deli_rag.reranking.base import Reranker
from deli_rag.retrieval.hybrid import HybridRetriever
from deli_rag.schemas import Filters


@dataclass
class PerItem:
    id: str
    question: str
    top_k: list[str]
    recall_at_5: float
    rr: float
    ndcg_at_5: float
    latency_ms: float


@dataclass
class EvalReport:
    k: int
    items: list[PerItem] = field(default_factory=list)
    recall_at_5: float = 0.0
    mrr: float = 0.0
    ndcg_at_5: float = 0.0
    avg_latency_ms: float = 0.0
    reranker_used: bool = False

    def to_dict(self) -> dict:
        return {
            "k": self.k,
            "n_items": len(self.items),
            "recall@5": round(self.recall_at_5, 4),
            "mrr": round(self.mrr, 4),
            "ndcg@5": round(self.ndcg_at_5, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "reranker_used": self.reranker_used,
        }


def run_eval(session: Session, embedder: Embedder, golden: GoldenSet, *,
             reranker: Reranker | None = None, k: int = 8) -> EvalReport:
    retriever = HybridRetriever(session, embedder, reranker=reranker)
    report = EvalReport(k=k, reranker_used=reranker is not None)

    for item in golden.items:
        if item.should_abstain:
            continue
        filters = Filters(acl_levels=item.acl_levels, tenant=item.tenant)
        t0 = time.perf_counter()
        result = retriever.search(item.question, filters=filters, k=k)
        dt_ms = (time.perf_counter() - t0) * 1000

        report.items.append(PerItem(
            id=item.id, question=item.question,
            top_k=[c.chunk_id for c in result.chunks],
            recall_at_5=recall_at_k(result.chunks, item, 5),
            rr=reciprocal_rank(result.chunks, item),
            ndcg_at_5=ndcg_at_k(result.chunks, item, 5),
            latency_ms=dt_ms,
        ))

    if report.items:
        report.recall_at_5 = sum(i.recall_at_5 for i in report.items) / len(report.items)
        report.mrr = sum(i.rr for i in report.items) / len(report.items)
        report.ndcg_at_5 = sum(i.ndcg_at_5 for i in report.items) / len(report.items)
        report.avg_latency_ms = sum(i.latency_ms for i in report.items) / len(report.items)

    return report