from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from deli_rag.config.settings import get_env
from deli_rag.embeddings.base import get_embedder
from deli_rag.retrieval.fusion import reciprocal_rank_fusion
from deli_rag.retrieval.hybrid import HybridRetriever
from deli_rag.retrieval.types import ScoredChunk
from deli_rag.schemas import Filters


def _mk(chunk_id: str, score: float | None = None) -> ScoredChunk:
    return ScoredChunk(
        chunk_id=chunk_id, doc_id="d1", doc_version=1, text=f"text-{chunk_id}",
        dense_score=score,
    )


# --- RRF unit tests (no DB) ---

def test_rrf_fuses_rankings():
    a = [_mk("c1"), _mk("c2"), _mk("c3")]
    b = [_mk("c3"), _mk("c1"), _mk("c4")]
    fused = reciprocal_rank_fusion(a, b, k=60)
    ids = [c.chunk_id for c in fused]
    assert ids[0] == "c1"
    assert ids[1] == "c3"
    assert set(ids) == {"c1", "c2", "c3", "c4"}


def test_rrf_handles_empty_lists():
    assert reciprocal_rank_fusion([]) == []
    a = [_mk("x")]
    assert [c.chunk_id for c in reciprocal_rank_fusion(a, [])] == ["x"]
    assert [c.chunk_id for c in reciprocal_rank_fusion([], a)] == ["x"]


def test_rrf_preserves_first_metadata():
    a = [_mk("c1")]
    a[0].dense_score = 0.9
    b = [_mk("c1")]
    b[0].keyword_score = 0.5
    fused = reciprocal_rank_fusion(a, b)
    assert fused[0].dense_score == 0.9
    assert fused[0].rrf_score is not None


# --- Integration (skips if DB has no embeddings) ---

@pytest.fixture(scope="module")
def session():
    try:
        engine = create_engine(get_env().database_url, future=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Postgres not reachable: {e}")
    s = Session(engine)
    yield s
    s.close()


def _has_embeddings(session) -> bool:
    return session.execute(text("SELECT COUNT(*) FROM embeddings")).scalar() > 0


def test_hybrid_returns_something_for_real_query(session):
    if not _has_embeddings(session):
        pytest.skip("no embeddings in DB; run `deli-rag index` first")
    retriever = HybridRetriever(session, get_embedder())
    result = retriever.search(
        "RIA money transfer commission",
        filters=Filters(acl_levels=["public", "internal"]),
    )
    assert result.chunks, "expected at least one chunk"
    assert result.dense_candidates > 0
    joined = " ".join(c.text.lower() for c in result.chunks[:5])
    assert "ria" in joined or "commission" in joined


def test_hybrid_respects_acl(session):
    if not _has_embeddings(session):
        pytest.skip("no embeddings in DB")
    retriever = HybridRetriever(session, get_embedder())
    result = retriever.search(
        "RIA", filters=Filters(acl_levels=["public"], tenant="default"),
    )
    for c in result.chunks:
        assert c.acl_level == "public"