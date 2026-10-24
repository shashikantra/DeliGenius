from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from deli_rag.agent.sql_route import SqlEvidence
from deli_rag.retrieval.types import ScoredChunk


Sufficiency = Literal["sufficient", "marginal", "insufficient"]


@dataclass
class SufficiencyReport:
    level: Sufficiency
    reason: str
    doc_count: int
    sql_count: int
    best_score: float


def check(
    doc_chunks: list[ScoredChunk],
    sql_evidence: list[SqlEvidence],
) -> SufficiencyReport:
    """Heuristic sufficiency check.

    Rules (conservative — we'd rather retry than answer weakly):
    - No evidence at all → insufficient.
    - SQL evidence present, no doc chunks → sufficient (SQL is precise).
    - Best doc score below 0.4 → insufficient.
    - Only one doc chunk and no SQL → marginal (thin evidence).
    - Otherwise → sufficient.
    """
    doc_count = len(doc_chunks)
    sql_count = len(sql_evidence)
    best_score = max((_score(c) for c in doc_chunks), default=0.0)

    if doc_count == 0 and sql_count == 0:
        return SufficiencyReport(
            level="insufficient",
            reason="no evidence retrieved",
            doc_count=0, sql_count=0, best_score=0.0,
        )

    if sql_count > 0 and doc_count == 0:
        return SufficiencyReport(
            level="sufficient",
            reason=f"{sql_count} SQL evidence block(s), no doc chunks needed",
            doc_count=0, sql_count=sql_count, best_score=0.0,
        )

    if best_score < 0.4:
        return SufficiencyReport(
            level="insufficient",
            reason=f"best doc score {best_score:.3f} below threshold 0.4",
            doc_count=doc_count, sql_count=sql_count, best_score=best_score,
        )

    if doc_count == 1 and sql_count == 0:
        return SufficiencyReport(
            level="marginal",
            reason="single doc chunk, no SQL support",
            doc_count=doc_count, sql_count=sql_count, best_score=best_score,
        )

    return SufficiencyReport(
        level="sufficient",
        reason=f"{doc_count} doc chunks, {sql_count} SQL blocks, "
               f"best score {best_score:.3f}",
        doc_count=doc_count, sql_count=sql_count, best_score=best_score,
    )


def _score(c: ScoredChunk) -> float:
    if c.rerank_score is not None:
        return c.rerank_score
    if c.rrf_score is not None:
        return c.rrf_score
    if c.dense_score is not None:
        return c.dense_score
    return 0.0