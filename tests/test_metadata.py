from __future__ import annotations

from pathlib import Path

from deli_rag.ingestion.dedup import decide
from deli_rag.ingestion.metadata import (
    _strip_date_suffixes, build_document, file_content_hash, logical_doc_id,
)
from deli_rag.ingestion.parsers.csv_parser import CsvParser
from deli_rag.schemas import ACL, Document, Timestamps
from datetime import datetime, timezone


FIXTURES = Path(__file__).parent / "fixtures" / "data"


def test_strip_date_suffixes_collapses_daily_reports():
    assert _strip_date_suffixes("Inventory_Status_Jun_21,_2026") == "Inventory_Status"
    assert _strip_date_suffixes("Sales_History_2026-06-21") == "Sales_History"
    assert _strip_date_suffixes("AgentBalanceReport_06_21_2026") == "AgentBalanceReport"
    assert _strip_date_suffixes("policy_sample") == "policy_sample"


def test_logical_doc_id_is_stable_across_daily_variants():
    a = logical_doc_id(Path("Inventory_Status_Jun_21,_2026.csv"), "local_folder")
    b = logical_doc_id(Path("Inventory_Status_Jun_22,_2026.csv"), "local_folder")
    assert a == b
    # Different series get different IDs
    c = logical_doc_id(Path("Sales_History_Jun_21,_2026.csv"), "local_folder")
    assert a != c


def test_content_hash_differs_for_different_bytes():
    a = file_content_hash(FIXTURES / "sales_sample.csv")
    b = file_content_hash(FIXTURES / "policy_sample.docx")
    assert a != b


def test_build_document_uses_default_acl():
    parsed = CsvParser().parse(FIXTURES / "sales_sample.csv")
    doc = build_document(
        path=FIXTURES / "sales_sample.csv",
        parsed=parsed,
        source_kind="local_folder",
    )
    assert doc.acl.level == "internal"
    assert doc.doc_type == "csv"
    assert doc.filename == "sales_sample.csv"
    assert doc.content_hash != ""


def _mk_doc(content_hash: str, version: int, doc_id: str = "abc") -> Document:
    now = datetime.now(timezone.utc)
    return Document(
        doc_id=doc_id, doc_version=version, source_kind="local_folder",
        source_ref="/x", filename="x", doc_type="csv", mime="text/csv",
        content_hash=content_hash, acl=ACL(level="internal"),
        timestamps=Timestamps(created_at=now, updated_at=now),
    )


def test_dedup_insert_when_no_prior():
    candidate = _mk_doc("h1", 1)
    d = decide(candidate=candidate, existing_versions=[])
    assert d.decision == "insert_new"
    assert d.doc_version == 1
    assert d.supersedes_doc_id is None


def test_dedup_skip_when_identical():
    prior = _mk_doc("h1", 1)
    candidate = _mk_doc("h1", 1)
    d = decide(candidate=candidate, existing_versions=[prior])
    assert d.decision == "skip_identical"
    assert d.doc_version == 1


def test_dedup_new_version_when_content_changed():
    prior = _mk_doc("h1", 1)
    candidate = _mk_doc("h2", 1)
    d = decide(candidate=candidate, existing_versions=[prior])
    assert d.decision == "new_version"
    assert d.doc_version == 2
    assert d.supersedes_doc_id == "abc"