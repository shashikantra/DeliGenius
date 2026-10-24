from __future__ import annotations

from deli_rag.agent.compress import compress
from deli_rag.retrieval.types import ScoredChunk


def _c(chunk_id: str, text: str, *, score: float = 0.5, page: int = 1,
       section: str = "S", doc_id: str = "d1") -> ScoredChunk:
    c = ScoredChunk(
        chunk_id=chunk_id, doc_id=doc_id, doc_version=1, text=text,
        page=page, section=section,
    )
    c.rrf_score = score
    return c


def test_compress_empty_input():
    out, report = compress([])
    assert out == []
    assert report.input_count == 0
    assert report.output_count == 0


def test_compress_dedups_identical_text():
    chunks = [_c("a", "same text"), _c("b", "same text"), _c("c", "other text")]
    out, report = compress(chunks)
    assert len(out) == 2
    assert report.duplicates_dropped == 1


def test_compress_drops_low_score_but_keeps_minimum():
    chunks = [
        _c("a", "top hit", score=0.9),
        _c("b", "mid hit", score=0.05),
        _c("c", "low hit", score=0.001),
        _c("d", "lower hit", score=0.0001),
        _c("e", "lowest hit", score=0.00001),
    ]
    out, report = compress(chunks)
    # min_chunks_to_keep is 3 by default
    assert len(out) >= 3
    assert "top hit" in out[0].text


def test_compress_respects_max_chunks():
    chunks = [_c(f"c{i}", f"text {i}", score=0.9 - i * 0.01) for i in range(20)]
    out, report = compress(chunks)
    assert len(out) <= 8


def test_compress_merges_adjacent_same_section():
    chunks = [
        _c("a", "page one content", score=0.9, page=1, section="S1"),
        _c("b", "page two content", score=0.8, page=2, section="S1"),
    ]
    out, report = compress(chunks)
    # Merged into one
    assert len(out) == 1
    assert "page one" in out[0].text
    assert "page two" in out[0].text
    assert report.merged_count == 1


def test_compress_does_not_merge_across_sections():
    chunks = [
        _c("a", "in section A", score=0.9, page=1, section="A"),
        _c("b", "in section B", score=0.8, page=2, section="B"),
    ]
    out, report = compress(chunks)
    assert len(out) == 2
    assert report.merged_count == 0


def test_compress_does_not_merge_distant_pages():
    chunks = [
        _c("a", "page 1", score=0.9, page=1, section="S"),
        _c("b", "page 5", score=0.8, page=5, section="S"),
    ]
    out, report = compress(chunks)
    assert len(out) == 2
    assert report.merged_count == 0


def test_compress_preserves_order_by_score():
    chunks = [
        _c("a", "top", score=0.9, page=1, section="A"),
        _c("b", "mid", score=0.5, page=1, section="B"),
        _c("c", "low", score=0.1, page=1, section="C"),
    ]
    out, _ = compress(chunks)
    scores = [c.rrf_score for c in out]
    assert scores == sorted(scores, reverse=True)


def test_compress_report_totals():
    chunks = [_c(f"c{i}", f"unique {i}", score=0.9 - i * 0.01) for i in range(5)]
    out, report = compress(chunks)
    assert report.input_count == 5
    assert report.output_count == len(out)
    assert report.total_tokens_out >= 0