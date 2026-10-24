from pydantic import BaseModel, Field


class Chunk(BaseModel):
    chunk_id: str
    parent_id: str | None = None
    doc_id: str
    doc_version: int
    page: int | None = None
    section: str | None = None
    text: str
    context_line: str = ""            # short doc/section prefix prepended before embedding
    content_hash: str
    token_count: int
    topic: str | None = None
    is_table: bool = False
    table_summary: str | None = None  # stored for retrieval when is_table
    acl_level: str = "internal"
    tenant: str = "default"
    groups: list[str] = Field(default_factory=list)
    language: str = "en"