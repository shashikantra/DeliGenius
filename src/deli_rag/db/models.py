from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("doc_id", "doc_version", name="uq_doc_version"),
        Index("ix_documents_content_hash", "content_hash"),
        Index("ix_documents_acl", "acl_level", "tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_version: Mapped[int] = mapped_column(Integer, default=1)
    source_kind: Mapped[str] = mapped_column(String(32))
    source_ref: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(String(32))
    mime: Mapped[str] = mapped_column(String(128))
    content_hash: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="en")
    acl_level: Mapped[str] = mapped_column(String(16), default="internal")
    tenant: Mapped[str] = mapped_column(String(64), default="default")
    groups: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    superseded_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    doc_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    chunks: Mapped[list["ChunkRow"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class ChunkRow(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_doc", "doc_id", "doc_version"),
        Index("ix_chunks_acl", "acl_level", "tenant"),
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("chunks.chunk_id"), nullable=True)
    doc_pk: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_version: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    context_line: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    token_count: Mapped[int] = mapped_column(Integer)
    topic: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_table: Mapped[bool] = mapped_column(Boolean, default=False)
    table_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    acl_level: Mapped[str] = mapped_column(String(16), default="internal")
    tenant: Mapped[str] = mapped_column(String(64), default="default")
    groups: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    language: Mapped[str] = mapped_column(String(8), default="en")
    tsv: Mapped[str] = mapped_column(TSVECTOR)   # populated by trigger in migration

    document: Mapped[DocumentRow] = relationship(back_populates="chunks")


class EmbeddingRow(Base):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "model_name", "model_version", name="uq_embed"),
        Index("ix_embeddings_hnsw", "vector", postgresql_using="hnsw",
              postgresql_ops={"vector": "vector_cosine_ops"}),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.chunk_id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(128))
    model_version: Mapped[str] = mapped_column(String(16))
    vector: Mapped[list[float]] = mapped_column(Vector(384))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLogRow(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), index=True)
    actor: Mapped[str] = mapped_column(String(64), default="anonymous")
    action: Mapped[str] = mapped_column(String(64))           # ingest | retrieve | answer
    doc_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())