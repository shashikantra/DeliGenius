from __future__ import annotations

from pathlib import Path

import pytest

from deli_rag.db.writer import DocumentWriter, existing_versions
from deli_rag.ingestion.chunker import Chunker
from deli_rag.ingestion.dedup import decide
from deli_rag.ingestion.metadata import build_document
from deli_rag.ingestion.parsers.csv_parser import CsvParser
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from deli_rag.config.settings import get_env


FIXTURES = Path(__file__).parent / "fixtures" / "data"


@pytest.fixture
def session():
    try:
        engine = create_engine(get_env().database_url, future=True)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception as e:
        pytest.skip(f"Postgres not reachable: {e}")
    s = Session(engine)
    yield s
    s.rollback()
    s.close()


def _ingest_fixture(session: Session, name: str, *, acl_level: str = "internal"):
    path = FIXTURES / name
    parsed = CsvParser().parse(path)
    doc = build_document(path=path, parsed=parsed, acl_level=acl_level)

    prior = existing_versions(session, doc.doc_id)
    decision = decide(candidate=doc, existing_versions=prior)
    if decision.decision == "skip_identical":
        return None, decision

    doc.doc_version = decision.doc_version
    chunks = Chunker().chunk(parsed, doc_id=doc.doc_id, doc_title=path.stem)
    writer = DocumentWriter(session)
    writer.write_document(doc=doc, chunks=chunks,
                          supersedes_doc_id=decision.supersedes_doc_id)
    session.flush()
    return doc, decision


def test_write_first_version_inserts_document_and_chunks(session):
    doc, decision = _ingest_fixture(session, "sales_sample.csv")
    if doc is None:
        pytest.skip("already ingested in DB; clean with: DELETE FROM documents WHERE doc_id=...")

    assert decision.decision == "insert_new"
    assert doc.doc_version == 1

    # Confirm DB rows
    count = session.execute(
        text("SELECT COUNT(*) FROM chunks WHERE doc_id = :d"), {"d": doc.doc_id}
    ).scalar()
    assert count > 0

    # Every chunk has ACL propagated from the doc
    acl = session.execute(
        text("SELECT DISTINCT acl_level FROM chunks WHERE doc_id = :d"), {"d": doc.doc_id}
    ).scalars().all()
    assert acl == ["internal"]


def test_write_second_identical_skips(session):
    # First ingest
    doc1, _ = _ingest_fixture(session, "policy_sample.docx") if False else (None, None)
    # Reuse CSV for simplicity
    _ingest_fixture(session, "sales_sample.csv")
    session.commit()

    # Second ingest of the same file
    _, decision2 = _ingest_fixture(session, "sales_sample.csv")
    assert decision2.decision == "skip_identical"