from datetime import datetime

from pydantic import BaseModel, Field


class Filters(BaseModel):
    """PRE-filters applied inside retrievers (never post-filtered)."""
    acl_levels: list[str] = Field(default_factory=lambda: ["public", "internal"])
    tenant: str = "default"
    groups: list[str] = Field(default_factory=list)
    doc_types: list[str] | None = None
    freshness_cutoff: datetime | None = None