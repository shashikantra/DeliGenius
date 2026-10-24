from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    acl: Literal["public", "internal", "confidential"] = "internal"
    k: int = Field(default=8, ge=1, le=24)
    rerank: bool = False
    model: str | None = None  # <--- ADD THIS
    history: list[tuple[str, str]] = Field(default_factory=list)


class CitationOut(BaseModel):
    id: int
    kind: str
    chunk_id: str | None = None
    filename: str | None = None
    page: int | None = None
    section: str | None = None
    sql_kind: str | None = None
    sql_summary: str | None = None
    sql_query: str | None = None        # <--- ADD THIS
    sql_data: list[list] | None = None  # <--- ADD THIS


class AskResponse(BaseModel):
    request_id: str
    answer: str
    citations: list[CitationOut] = Field(default_factory=list)
    confidence: float
    abstained: bool
    needs_clarification: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    reason: str = ""
    model_used: str | None = None
    iterations_used: int = 0
    elapsed_s: float = 0.0


class FeedbackRequest(BaseModel):
    request_id: str
    question: str
    answer: str
    vote: Literal["up", "down"]
    comment: str | None = None


class FeedbackResponse(BaseModel):
    ok: bool
    request_id: str


class ModelInfo(BaseModel):
    id: str
    primary: bool = False
    verified: bool = True


class ModelsResponse(BaseModel):
    models: list[ModelInfo]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    db: bool
    groq: bool
    embedder_loaded: bool
    request_id: str

class DocumentOut(BaseModel):
    doc_id: str
    doc_version: int
    filename: str
    doc_type: str
    mime: str
    acl_level: str
    chunk_count: int
    superseded_by: str | None = None
    created_at: str           # ISO-8601 string
    size_bytes: int = 0


class DocumentsResponse(BaseModel):
    documents: list[DocumentOut]
    total: int


class ChunkOut(BaseModel):
    chunk_id: str
    parent_id: str | None = None
    page: int | None = None
    section: str | None = None
    text: str
    token_count: int
    is_table: bool = False
    context_line: str = ""


class DocumentDetailResponse(BaseModel):
    document: DocumentOut
    chunks: list[ChunkOut]
    total_chunks: int


class DebugInfo(BaseModel):
    trace: list[str] = Field(default_factory=list)
    iterations_used: int = 0
    elapsed_s: float = 0.0


class AskResponseWithDebug(AskResponse):
    """Same shape as AskResponse plus optional debug info."""
    debug: DebugInfo | None = None


class FeedbackOut(BaseModel):
    request_id: str
    vote: str
    question: str
    answer: str
    comment: str | None = None
    created_at: str


class FeedbackListResponse(BaseModel):
    feedback: list[FeedbackOut]
    total: int