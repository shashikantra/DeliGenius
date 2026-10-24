from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from pydantic import BaseModel, Field, field_validator

ElementKind = Literal["heading", "paragraph", "list_item", "table", "caption", "footer", "page_number"]

def _sanitize_text(val: str | None) -> str | None:
    """Remove NUL (0x00) bytes which crash PostgreSQL."""
    if val is None:
        return None
    return str(val).replace("\x00", "")


class ParsedElement(BaseModel):
    kind: ElementKind
    text: str
    level: int | None = None
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    rows: list[list[str]] | None = None
    caption: str | None = None
    meta: dict = Field(default_factory=dict)

    @field_validator("text", "caption", mode="before")
    @classmethod
    def clean_text_fields(cls, v):
        return _sanitize_text(v)

    @field_validator("rows", mode="before")
    @classmethod
    def clean_rows(cls, v):
        if not v:
            return v
        return [[_sanitize_text(c) for c in row] for row in v]


class ParsedPage(BaseModel):
    number: int
    elements: list[ParsedElement] = Field(default_factory=list)

class TableRecord(BaseModel):
    """Numeric/structured payload extracted from a source document.
    Consumer: the Track-2 SQL loader (Commit #6). Not chunked for RAG."""
    name: str
    columns: list[str]
    rows: list[list[str]]
    page: int | None = None
    source_path: str
    meta: dict = Field(default_factory=dict)

    @field_validator("columns", mode="before")
    @classmethod
    def clean_cols(cls, v):
        return [_sanitize_text(c) for c in v]

    @field_validator("rows", mode="before")
    @classmethod
    def clean_rows(cls, v):
        if not v:
            return v
        return [[_sanitize_text(c) for c in row] for row in v]

class ParsedDocument(BaseModel):
    source_path: str
    mime: str
    pages: list[ParsedPage] = Field(default_factory=list)
    tables: list[TableRecord] = Field(default_factory=list)   # NEW
    metadata: dict = Field(default_factory=dict)
    parser_name: str
    parser_version: str = "1"


class Parser(Protocol):
    name: ClassVar[str]
    supported_mimes: ClassVar[set[str]]
    supported_extensions: ClassVar[set[str]]

    def parse(self, path: Path) -> ParsedDocument: ...


_PARSER_REGISTRY: list[type] = []


def register(cls: type) -> type:
    _PARSER_REGISTRY.append(cls)
    return cls


def get_parser_for(path: Path) -> Parser:
    ext = path.suffix.lower()
    name_lower = path.name.lower()

    # 1. Check specific filename patterns FIRST (so Sales_History matches sales_csv)
    for cls in _PARSER_REGISTRY:
        parser_name = getattr(cls, "name", "")
        if parser_name == "sales_csv" and "sales" in name_lower:
            return cls()
        if parser_name == "ria" and ("ria" in name_lower or "agentbalance" in name_lower):
            return cls()
        if parser_name == "lottery" and "lottery" in name_lower:
            return cls()

    # 2. Fall back to longest-suffix match (so ".ria.pdf" beats ".pdf").
    best: type | None = None
    best_len = 0
    for cls in _PARSER_REGISTRY:
        for suffix in getattr(cls, "supported_extensions", set()):
            if name_lower.endswith(suffix) and len(suffix) > best_len:
                best = cls
                best_len = len(suffix)
    if best is not None:
        return best()  # type: ignore[call-arg]

    # 3. Fall back to MIME type
    mime, _ = mimetypes.guess_type(str(path))
    if mime:
        for cls in _PARSER_REGISTRY:
            if mime in getattr(cls, "supported_mimes", set()):
                return cls()  # type: ignore[call-arg]

    raise ValueError(f"No parser registered for {path.name!r} (ext={ext!r}, mime={mime!r})")

# def get_parser_for(path: Path) -> Parser:
#     ext = path.suffix.lower()
#     name_lower = path.name.lower()
#     # Longest-suffix match wins (so ".ria.pdf" beats ".pdf").
#     best: type | None = None
#     best_len = 0
#     for cls in _PARSER_REGISTRY:
#         for suffix in getattr(cls, "supported_extensions", set()):
#             if name_lower.endswith(suffix) and len(suffix) > best_len:
#                 best = cls
#                 best_len = len(suffix)
#     if best is not None:
#         return best()  # type: ignore[call-arg]
#     mime, _ = mimetypes.guess_type(str(path))
#     if mime:
#         for cls in _PARSER_REGISTRY:
#             if mime in getattr(cls, "supported_mimes", set()):
#                 return cls()  # type: ignore[call-arg]
#     raise ValueError(f"No parser registered for {path.name!r} (ext={ext!r}, mime={mime!r})")
