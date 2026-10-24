from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A reference to a piece of evidence used in the answer."""
    id: int                          # 1-based, matches [N] in the prompt and answer text
    kind: Literal["doc", "sql"]
    # doc citations
    chunk_id: str | None = None
    filename: str | None = None
    page: int | None = None
    section: str | None = None
    # sql citations
    sql_kind: str | None = None
    sql_summary: str | None = None
    sql_query: str | None = None         # <--- ADD THIS
    sql_data: list[list] | None = None   # <--- ADD THIS


class Answer(BaseModel):
    """Strict schema the LLM must emit. Any deviation → validation failure."""
    answer: str
    citations: list[int] = Field(default_factory=list)   # which [N] IDs the answer relies on
    confidence: float = Field(ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)
    needs_clarification: str | None = None
    abstained: bool = False
    reason: str = ""                 # if abstained or low confidence