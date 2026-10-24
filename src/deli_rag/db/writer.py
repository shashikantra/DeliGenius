from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from deli_rag.db.models import (
    ChunkRow, DocumentRow, EmbeddingRow, AuditLogRow, Base,
)
from deli_rag.ingestion.chunker import DraftChunk
from deli_rag.schemas import Document


class DocumentWriter:
    """Transactional persistence for Document + Chunk rows.

    Contract:
    - One call to `write_document` inserts the Document row and all Chunk rows in
      a single transaction. If any chunk fails, everything rolls back.
    - `supersede` marks the previous version's `superseded_by` field — it does NOT
      delete it. Tombstones keep audit trail and let retrieval down-weight stale
      content.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def write_document(
        self,
        *,
        doc: Document,
        chunks: list[DraftChunk],
        supersedes_doc_id: str | None = None,
    ) -> DocumentRow:
        row = DocumentRow(
            doc_id=doc.doc_id,
            doc_version=doc.doc_version,
            source_kind=doc.source_kind,
            source_ref=doc.source_ref,
            filename=doc.filename,
            doc_type=doc.doc_type,
            mime=doc.mime,
            content_hash=doc.content_hash,
            language=doc.language,
            acl_level=doc.acl.level,
            tenant=doc.acl.tenant,
            groups=doc.acl.groups,
            superseded_by=None,
            doc_metadata={},
        )
        self.session.add(row)
        self.session.flush()   # get row.id for FK

        for c in chunks:
            self.session.add(ChunkRow(
                chunk_id=c.chunk_id,
                parent_id=c.parent_id,
                doc_pk=row.id,
                doc_id=doc.doc_id,
                doc_version=doc.doc_version,
                page=c.page,
                section=c.section,
                text=c.text,
                context_line=c.context_line,
                content_hash=c.content_hash,
                token_count=c.token_count,
                topic=None,
                is_table=c.is_table,
                table_summary=c.table_summary,
                acl_level=doc.acl.level,
                tenant=doc.acl.tenant,
                groups=doc.acl.groups,
                language=doc.language,
            ))

        if supersedes_doc_id is not None:
            self._mark_superseded(supersedes_doc_id, superseding_doc_id=doc.doc_id)

        self._audit("ingest", doc_id=doc.doc_id, chunk_ids=[c.chunk_id for c in chunks])
        self.session.flush()
        return row

    def _mark_superseded(self, old_doc_id: str, *, superseding_doc_id: str) -> None:
        stmt = (
            select(DocumentRow)
            .where(DocumentRow.doc_id == old_doc_id)
            .order_by(DocumentRow.doc_version.desc())
        )
        latest = self.session.execute(stmt).scalars().first()
        if latest is not None:
            latest.superseded_by = superseding_doc_id
            latest.updated_at = datetime.now(timezone.utc)

    def _audit(self, action: str, *, doc_id: str, chunk_ids: list[str]) -> None:
        self.session.add(AuditLogRow(
            request_id=None,
            actor="system",
            action=action,
            doc_id=doc_id,
            chunk_ids=chunk_ids,
            detail={},
        ))


def existing_versions(session: Session, doc_id: str) -> list[Document]:
    """Load prior versions of a logical doc as plain Document schemas."""
    rows = session.execute(
        select(DocumentRow).where(DocumentRow.doc_id == doc_id).order_by(DocumentRow.doc_version)
    ).scalars().all()
    out: list[Document] = []
    for r in rows:
        out.append(Document(
            doc_id=r.doc_id,
            doc_version=r.doc_version,
            source_kind=r.source_kind,
            source_ref=r.source_ref,
            filename=r.filename,
            doc_type=r.doc_type,
            mime=r.mime,
            content_hash=r.content_hash,
            language=r.language,
            acl={
                "level": r.acl_level,
                "tenant": r.tenant,
                "groups": list(r.groups or []),
            },
            timestamps={
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            },
            superseded_by=r.superseded_by,
        ))
    return out


def session_scope():
    """Standalone session context manager for use outside FastAPI/CLI."""
    from sqlalchemy import create_engine
    from deli_rag.config.settings import get_env
    engine = create_engine(get_env().database_url, future=True)
    return Session(engine)