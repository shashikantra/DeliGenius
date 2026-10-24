from __future__ import annotations

from deli_rag.eval.golden import GoldenItem
from deli_rag.eval.metrics import ndcg_at_k, recall_at_k, reciprocal_rank
from deli_rag.retrieval.types import ScoredChunk


def _c(chunk_id: str, text: str) -> ScoredChunk:
    return ScoredChunk(chunk_id=chunk_id, doc_id="d", doc_version=1, text=text)


def test_recall_at_k_hits_when_substring_present():
    item = GoldenItem(id="x", question="q", expected_substrings=["commission"])
    chunks = [_c("a", "irrelevant"), _c("b", "RIA commission accrued 13.35")]
    assert recall_at_k(chunks, item, 5) == 1.0


def test_recall_at_k_misses_when_substring_absent():
    item = GoldenItem(id="x", question="q", expected_substrings=["commission"])
    chunks = [_c("a", "irrelevant"), _c("b", "also irrelevant")]
    assert recall_at_k(chunks, item, 5) == 0.0


def test_recall_respects_k():
    item = GoldenItem(id="x", question="q", expected_substrings=["hit"])
    chunks = [_c("a", "no"), _c("b", "no"), _c("c", "no"), _c("d", "no"),
              _c("e", "no"), _c("f", "hit")]
    assert recall_at_k(chunks, item, 5) == 0.0
    assert recall_at_k(chunks, item, 6) == 1.0


def test_reciprocal_rank_first_position():
    item = GoldenItem(id="x", question="q", expected_substrings=["hit"])
    assert reciprocal_rank([_c("a", "hit")], item) == 1.0
    assert reciprocal_rank([_c("a", "no"), _c("b", "hit")], item) == 0.5


def test_ndcg_at_k_perfect_ordering():
    item = GoldenItem(id="x", question="q", expected_substrings=["hit"])
    assert ndcg_at_k([_c("a", "hit")], item, 5) == 1.0