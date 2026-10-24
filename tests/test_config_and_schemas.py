from datetime import datetime, timezone

from deli_rag.config.settings import get_config
from deli_rag.schemas import ACL, Chunk, Document, Filters, Timestamps


def test_config_loads_and_matches_contract():
    cfg = get_config()
    assert cfg.embedder.dim == 384
    assert cfg.embedder.name == "BAAI/bge-small-en-v1.5"
    assert cfg.llm.primary.id == "openai/gpt-oss-20b"
    assert cfg.llm.fallback_2.verified is False        # Qwen stays gated
    assert cfg.chunking.child_max_tokens >= cfg.chunking.child_target_tokens
    assert cfg.access.default_email_acl == "internal"


def test_document_schema_requires_hash_and_acl():
    now = datetime.now(timezone.utc)
    d = Document(
        doc_id="abc", doc_version=1, source_kind="local_folder",
        source_ref="/inbox/report.pdf", filename="report.pdf",
        doc_type="pdf", mime="application/pdf", content_hash="0" * 64,
        acl=ACL(level="internal"), timestamps=Timestamps(created_at=now, updated_at=now),
    )
    assert d.superseded_by is None


def test_chunk_defaults_and_acl():
    c = Chunk(chunk_id="c1", doc_id="abc", doc_version=1, text="hello",
              content_hash="h", token_count=1)
    assert c.acl_level == "internal"
    assert c.is_table is False


def test_filters_default_acl_is_safe():
    f = Filters()
    assert "confidential" not in f.acl_levels   # default excludes highest tier