"""initial schema: documents, chunks, embeddings, audit_log"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from pgvector.sqlalchemy import Vector

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "documents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("doc_id", sa.String(64), nullable=False, index=True),
        sa.Column("doc_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.Text, nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("doc_type", sa.String(32), nullable=False),
        sa.Column("mime", sa.String(128), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("language", sa.String(8), server_default="en"),
        sa.Column("acl_level", sa.String(16), server_default="internal"),
        sa.Column("tenant", sa.String(64), server_default="default"),
        sa.Column("groups", ARRAY(sa.String), server_default="{}"),
        sa.Column("superseded_by", sa.String(64), nullable=True),
        sa.Column("doc_metadata", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("doc_id", "doc_version", name="uq_doc_version"),
    )
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])
    op.create_index("ix_documents_acl", "documents", ["acl_level", "tenant"])

    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.String(64), primary_key=True),
        sa.Column("parent_id", sa.String(64), sa.ForeignKey("chunks.chunk_id"), nullable=True),
        sa.Column("doc_pk", sa.Integer, sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("doc_id", sa.String(64), nullable=False, index=True),
        sa.Column("doc_version", sa.Integer, nullable=False),
        sa.Column("page", sa.Integer, nullable=True),
        sa.Column("section", sa.Text, nullable=True),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("context_line", sa.Text, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("topic", sa.String(128), nullable=True),
        sa.Column("is_table", sa.Boolean, server_default=sa.false()),
        sa.Column("table_summary", sa.Text, nullable=True),
        sa.Column("acl_level", sa.String(16), server_default="internal"),
        sa.Column("tenant", sa.String(64), server_default="default"),
        sa.Column("groups", ARRAY(sa.String), server_default="{}"),
        sa.Column("language", sa.String(8), server_default="en"),
        sa.Column("tsv", TSVECTOR, nullable=True),
    )
    op.create_index("ix_chunks_doc", "chunks", ["doc_id", "doc_version"])
    op.create_index("ix_chunks_acl", "chunks", ["acl_level", "tenant"])
    op.create_index("ix_chunks_tsv", "chunks", ["tsv"], postgresql_using="gin")

    # tsv auto-populated from text + context_line
    op.execute("""
        CREATE FUNCTION chunks_tsv_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsv := to_tsvector('english', coalesce(NEW.context_line,'') || ' ' || coalesce(NEW.text,''));
          RETURN NEW;
        END $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_chunks_tsv
        BEFORE INSERT OR UPDATE ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_tsv_update();
    """)

    op.create_table(
        "embeddings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("chunk_id", sa.String(64), sa.ForeignKey("chunks.chunk_id", ondelete="CASCADE"), index=True),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(16), nullable=False),
        sa.Column("vector", Vector(384), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("chunk_id", "model_name", "model_version", name="uq_embed"),
    )
    op.execute("""
        CREATE INDEX ix_embeddings_hnsw ON embeddings
        USING hnsw (vector vector_cosine_ops);
    """)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_id", sa.String(64), index=True),
        sa.Column("actor", sa.String(64), server_default="anonymous"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("doc_id", sa.String(64), nullable=True),
        sa.Column("chunk_ids", ARRAY(sa.String), server_default="{}"),
        sa.Column("detail", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_chunks_tsv ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsv_update()")
    op.drop_table("audit_log")
    op.drop_table("embeddings")
    op.drop_table("chunks")
    op.drop_table("documents")