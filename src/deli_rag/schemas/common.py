from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ACLLevel = Literal["public", "internal", "confidential"]
DocType = Literal["pdf", "docx", "xlsx", "csv", "ria_pdf", "lottery_pdf", "other"]
SourceKind = Literal["local_folder", "gmail"]


class ACL(BaseModel):
    level: ACLLevel = "internal"
    tenant: str = "default"
    groups: list[str] = Field(default_factory=list)


class Timestamps(BaseModel):
    created_at: datetime
    updated_at: datetime