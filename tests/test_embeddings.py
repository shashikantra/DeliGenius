from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from deli_rag.config.settings import get_env
from deli_rag.db.writer import DocumentWriter
from deli_rag.embeddings.base import get_embedder
from deli_rag.embeddings.indexer import Indexer
from deli_rag.ingestion.chunker import Chunker
from deli_rag.ingestion.metadata import build_document
from deli_rag.ingestion.parsers.csv_parser import CsvParser


FIXTURES = Path(__file__).parent / "fixtures" / "data"


@pytest.fixture(scope="module")
def session():
    try:
        engine = create_engine(get_env().database_url, future=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Postgres not reachable: {e}")
    s = Session(engine)
    yield s
    s.close()


@pytest.fixture(scope="module")
def embedder():
    return get_embedder()


# --- embedder contract ---

def test_embedder_dim_matches_config(embedder):
    vec = embedder.embed_query("how many items are low in stock?")
    assert len(vec) == embedder.dim


def test_embedder_documents_and_query_same_dim(embedder):
    vecs = embedder.embed_documents(["a", "b", "c"])
    assert len(vecs) == 3
    assert all(len(v) == embedder.dim for v in vecs)
    q = embedder.embed_query("a")
    assert len(q) == embedder.dim


def test_embedder_documents_idempotent(embedder):
    a = embedder.embed_documents(["reorder threshold"])[0]
    b = embedder.embed_documents(["reorder threshold"])[0]
    # Same input → same vector (deterministic inference)
    assert a == b


def test_embedder_normalized(embedder):
    v = embedder.embed_query("any text")
    norm_sq = sum(x * x for x in v)
    assert abs(norm_sq - 1.0) < 1e-3     # cosine-normalized


# --- indexer integration ---

def test_indexer_embeds_chunks_and_is_idempotent(session, embedder):
    path = FIXTURES / "sales_sample.csv"
    parsed = CsvParser().parse(path)
    doc = build_document(path=path, parsed=parsed, acl_level="internal")

    # Ensure clean state for this test's doc
    session.execute(text("DELETE FROM embeddings WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE doc_id = :d)"), {"d": doc.doc_id})
    session.execute(text("DELETE FROM chunks WHERE doc_id = :d"), {"d": doc.doc_id})
    session.execute(text("DELETE FROM documents WHERE doc_id = :d"), {"d": doc.doc_id})
    session.commit()

    chunks = Chunker().chunk(parsed, doc_id=doc.doc_id, doc_title=path.stem)
    DocumentWriter(session).write_document(doc=doc, chunks=chunks)
    session.commit()

    # First index run
    r1 = Indexer(session, embedder).index_all(doc_ids=[doc.doc_id])
    session.commit()
    assert r1.chunks_embedded > 0
    assert r1.chunks_embedded == r1.chunks_scanned

    # Second run — everything already embedded
    r2 = Indexer(session, embedder).index_all(doc_ids=[doc.doc_id])
    session.commit()
    assert r2.chunks_scanned == 0
    assert r2.chunks_embedded == 0

    # Confirm each chunk has exactly one embedding
    count = session.execute(text(
        "SELECT COUNT(*) FROM embeddings WHERE chunk_id IN "
        "(SELECT chunk_id FROM chunks WHERE doc_id = :d)"
    ), {"d": doc.doc_id}).scalar()
    assert count == len(chunks)