from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from deli_rag.retrieval.types import ScoredChunk
from deli_rag.schemas import Filters


_SQL = text("""
    SELECT c.chunk_id,
           c.parent_id,
           c.doc_id,
           c.doc_version,
           c.page,
           c.section,
           c.text,
           c.context_line,
           c.is_table,
           c.acl_level,
           c.tenant,
           d.filename,
           d.doc_type,
           ts_rank_cd(c.tsv, plainto_tsquery('english', :q)) AS keyword_score
    FROM chunks c
    JOIN documents d ON d.id = c.doc_pk
    WHERE c.tsv @@ plainto_tsquery('english', :q)
      AND c.acl_level = ANY(:acl_levels)
      AND c.tenant = :tenant
      AND d.superseded_by IS NULL
    ORDER BY keyword_score DESC
    LIMIT :k
""")


class KeywordRetriever:
    """Postgres full-text over `tsv` (BM25-ish via ts_rank_cd).
    Pre-filters ACL + supersession inside SQL."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def search(self, query: str, *, k: int, filters: Filters) -> list[ScoredChunk]:
        rows = self.session.execute(_SQL, {
            "q": query,
            "acl_levels": filters.acl_levels,
            "tenant": filters.tenant,
            "k": k,
        }).all()
        return [
            ScoredChunk(
                chunk_id=r.chunk_id, parent_id=r.parent_id,
                doc_id=r.doc_id, doc_version=r.doc_version,
                filename=r.filename, doc_type=r.doc_type,
                page=r.page, section=r.section,
                text=r.text, context_line=r.context_line,
                is_table=r.is_table, acl_level=r.acl_level, tenant=r.tenant,
                keyword_score=float(r.keyword_score) if r.keyword_score is not None else None,
            )
            for r in rows
        ]