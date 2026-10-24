from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from deli_rag.config.settings import get_config
from deli_rag.ingestion.parsers.base import ParsedDocument
from deli_rag.schemas import ACL, Document, Timestamps


def file_content_hash(path: Path, *, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of the file's raw bytes. Chunked read so large files don't blow memory."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk_size)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def logical_doc_id(path: Path, source_kind: str = "local_folder") -> str:
    """Stable identity for a logical document, independent of file bytes.

    For local folder intake, this is `source_kind::filename`. Two versions of the
    same filename (e.g. Inventory_Status_Jun_21 then Inventory_Status_Jun_22)
    would get *different* doc_ids because the filenames differ.

    For versioning to work correctly across daily reports we *want* the same
    logical doc_id per logical series. Two strategies:
      - (a) filename-as-identity: same filename = same doc → new version
      - (b) series-identity: strip dates from the filename and use the stem
    We use (b) via `_strip_date_suffixes()`. If the caller wants (a), they can
    pass the raw filename as `source_ref` instead.
    """
    stem = _strip_date_suffixes(path.stem)
    key = f"{source_kind}::{stem.lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def _strip_date_suffixes(stem: str) -> str:
    """Remove trailing date-like tokens so daily reports collapse to one series.

    Examples:
      Inventory_Status_Jun_21,_2026   → Inventory_Status
      Sales_History_2026-06-21        → Sales_History
      AgentBalanceReport_06_21_2026   → AgentBalanceReport
    """
    import re
    # Collapse anything after the first date-ish token, plus trailing separators
    patterns = [
        r"[_\-\s]+\d{4}[_\-]\d{1,2}[_\-]\d{1,2}.*$",     # 2026-06-21 or 2026_06_21
        r"[_\-\s]+[A-Za-z]{3}[_\-]\d{1,2}[,_\s]+\d{4}.*$", # Jun_21,_2026
        r"[_\-\s]+\d{1,2}[_\-]\d{1,2}[_\-]\d{2,4}.*$",   # 06_21_2026
    ]
    out = stem
    for p in patterns:
        out = re.sub(p, "", out, flags=re.IGNORECASE)
    return out.rstrip("_-,. ")


def build_document(
    *,
    path: Path,
    parsed: ParsedDocument,
    source_kind: str = "local_folder",
    acl_level: str | None = None,
    tenant: str = "default",
    groups: list[str] | None = None,
    doc_version: int = 1,
    mime: str | None = None,
) -> Document:
    cfg = get_config()
    acl = ACL(
        level=acl_level or cfg.access.default_email_acl,   # "internal"
        tenant=tenant,
        groups=groups or [],
    )
    now = datetime.now(timezone.utc)
    guessed_mime = mime or parsed.mime or (mimetypes.guess_type(str(path))[0] or "application/octet-stream")
    return Document(
        doc_id=logical_doc_id(path, source_kind),
        doc_version=doc_version,
        source_kind=source_kind,
        source_ref=str(path),
        filename=path.name,
        doc_type=_classify_doc_type(path, parsed.parser_name),
        mime=guessed_mime,
        content_hash=file_content_hash(path),
        language="en",
        acl=acl,
        timestamps=Timestamps(created_at=now, updated_at=now),
        superseded_by=None,
    )


def _classify_doc_type(path: Path, parser_name: str) -> str:
    name = path.name.lower()
    if ".ria." in name or parser_name == "ria":
        return "ria_pdf"
    if ".lottery." in name or parser_name == "lottery":
        return "lottery_pdf"
    if parser_name == "csv" or parser_name == "sales_csv":
        return "csv"
    if parser_name == "xlsx":
        return "xlsx"
    if parser_name == "docx":
        return "docx"
    if parser_name == "pdf":
        return "pdf"
    return "other"