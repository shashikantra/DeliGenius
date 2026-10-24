from __future__ import annotations

from pydantic import BaseModel, Field


class ScoredChunk(BaseModel):
    """A retrieved chunk with its score and provenance."""
    chunk_id: str
    parent_id: str | None = None
    doc_id: str
    doc_version: int
    filename: str | None = None
    doc_type: str | None = None
    page: int | None = None
    section: str | None = None
    text: str
    context_line: str = ""
    is_table: bool = False
    acl_level: str = "internal"
    tenant: str = "default"

    # Scoring — populated per-stage so we can audit the pipeline
    dense_score: float | None = None
    keyword_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None


class RetrievalResult(BaseModel):
    """The full output of the retrieval pipeline."""
    query: str
    chunks: list[ScoredChunk] = Field(default_factory=list)
    dense_candidates: int = 0
    keyword_candidates: int = 0
    fused_candidates: int = 0
    filtered_out_acl: int = 0