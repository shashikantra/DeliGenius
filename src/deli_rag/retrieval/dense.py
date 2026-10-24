from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from deli_rag.embeddings.base import Embedder
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
           1 - (e.vector <=> CAST(:qvec AS vector)) AS dense_score
    FROM embeddings e
    JOIN chunks c ON c.chunk_id = e.chunk_id
    JOIN documents d ON d.id = c.doc_pk
    WHERE e.model_name = :model_name
      AND e.model_version = :model_version
      AND c.acl_level = ANY(:acl_levels)
      AND c.tenant = :tenant
      AND d.superseded_by IS NULL
    ORDER BY e.vector <=> CAST(:qvec AS vector)
    LIMIT :k
""")


class DenseRetriever:
    """pgvector cosine similarity. Pre-filters ACL and supersession inside SQL,
    so no disallowed chunk ever leaves the database."""

    def __init__(self, session: Session, embedder: Embedder) -> None:
        self.session = session
        self.embedder = embedder

    def search(self, query: str, *, k: int, filters: Filters) -> list[ScoredChunk]:
        qvec = self.embedder.embed_query(query)
        qvec_str = "[" + ",".join(f"{x:.8f}" for x in qvec) + "]"
        rows = self.session.execute(_SQL, {
            "qvec": qvec_str,
            "model_name": self.embedder.name,
            "model_version": self.embedder.model_version,
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
                dense_score=float(r.dense_score) if r.dense_score is not None else None,
            )
            for r in rows
        ]