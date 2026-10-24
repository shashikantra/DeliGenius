from pydantic import BaseModel

from .common import ACL, DocType, SourceKind, Timestamps


class Document(BaseModel):
    doc_id: str                       # stable logical id (hash of source + logical name)
    doc_version: int = 1
    source_kind: SourceKind
    source_ref: str                   # path or gmail message id
    filename: str
    doc_type: DocType
    mime: str
    content_hash: str                 # sha256 of raw bytes
    language: str = "en"
    acl: ACL
    timestamps: Timestamps
    superseded_by: str | None = None  # doc_id of the version that replaces this one