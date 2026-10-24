from __future__ import annotations

from deli_rag.agent.sufficiency import check
from deli_rag.retrieval.types import ScoredChunk


def _c(score: float | None = None, rrf: float | None = None) -> ScoredChunk:
    c = ScoredChunk(chunk_id="x", doc_id="d", doc_version=1, text="t")
    c.rerank_score = score
    c.rrf_score = rrf
    return c


def test_no_evidence_insufficient():
    r = check([], [])
    assert r.level == "insufficient"


def test_low_score_insufficient():
    r = check([_c(rrf=0.1), _c(rrf=0.2)], [])
    assert r.level == "insufficient"


def test_single_doc_marginal():
    r = check([_c(rrf=0.8)], [])
    assert r.level == "marginal"


def test_multiple_docs_sufficient():
    r = check([_c(rrf=0.8), _c(rrf=0.7)], [])
    assert r.level == "sufficient"


def test_sql_only_sufficient():
    class FakeEv:
        kind = "ria_summary"
        summary = "7 rows"
    r = check([], [FakeEv()])
    assert r.level == "sufficient"