from __future__ import annotations

from deli_rag.config.settings import get_config
from deli_rag.ingestion.chunker import Chunker
from deli_rag.ingestion.parsers.base import (
    ParsedDocument, ParsedElement, ParsedPage,
)
from deli_rag.ingestion.parsers.csv_parser import CsvParser
from deli_rag.ingestion.parsers.docx_parser import DocxParser
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures" / "data"


def _make_doc(elements: list[ParsedElement]) -> ParsedDocument:
    return ParsedDocument(
        source_path="synthetic",
        mime="text/plain",
        pages=[ParsedPage(number=1, elements=elements)],
        metadata={},
        parser_name="synthetic",
    )


def test_chunker_splits_on_headings_and_parents_children():
    doc = _make_doc([
        ParsedElement(kind="heading", text="Refund Policy", level=1),
        ParsedElement(kind="paragraph", text="Refunds accepted within 30 days."),
        ParsedElement(kind="paragraph", text="Manager approval for over $50."),
        ParsedElement(kind="heading", text="Store Hours", level=1),
        ParsedElement(kind="paragraph", text="Mon-Sat 7am-9pm."),
    ])
    chunks = Chunker().chunk(doc, doc_id="d1", doc_title="Policy Doc")
    parents = [c for c in chunks if c.parent_id is None]
    children = [c for c in chunks if c.parent_id is not None]
    assert len(parents) == 2               # two sections
    assert len(children) >= 2
    # Parent section titles come from breadcrumbs
    assert any("Refund Policy" in (p.section or "") for p in parents)
    assert any("Store Hours" in (p.section or "") for p in parents)
    # Every child references a real parent
    parent_ids = {p.chunk_id for p in parents}
    assert all(c.parent_id in parent_ids for c in children)


def test_chunker_keeps_tables_whole():
    doc = _make_doc([
        ParsedElement(kind="heading", text="Hours", level=1),
        ParsedElement(kind="table", text="Day | Open\nMon-Sat | 07:00",
                      rows=[["Day", "Open"], ["Mon-Sat", "07:00"]],
                      caption="Store hours"),
        ParsedElement(kind="paragraph", text="Closed on major holidays."),
    ])
    chunks = Chunker().chunk(doc, doc_id="d2", doc_title="Hours Doc")
    table_children = [c for c in chunks if c.is_table]
    assert len(table_children) == 1
    t = table_children[0]
    assert "Store hours" in t.text             # caption preserved
    assert "Mon-Sat" in t.text
    assert t.table_summary and "1 rows" in t.table_summary


def test_chunker_context_line_and_token_budget():
    cfg = get_config().chunking
    doc = _make_doc([
        ParsedElement(kind="heading", text="Big Section", level=1),
        *[ParsedElement(kind="paragraph", text=f"Sentence number {i}. " * 30)
          for i in range(5)],
    ])
    chunks = Chunker().chunk(doc, doc_id="d3", doc_title="Big Doc")
    children = [c for c in chunks if c.parent_id is not None]
    assert children
    for c in children:
        assert c.context_line.startswith("Big Doc")
        assert c.token_count <= cfg.child_max_tokens + 50   # small slack


def test_chunker_hashes_identical_content_identically():
    """Two identical *chunks* (not two identical paragraphs) get the same hash.
    Chunker output: N elements packed into a chunk. If we force two chunks with
    identical content (via two separate sections with the same text), their
    content_hash must match."""
    same = "Identical text appears twice with the same wording."
    doc = _make_doc([
        ParsedElement(kind="heading", text="Section A", level=1),
        ParsedElement(kind="paragraph", text=same),
        ParsedElement(kind="heading", text="Section B", level=1),
        ParsedElement(kind="paragraph", text=same),
    ])
    chunks = Chunker().chunk(doc, doc_id="d4", doc_title="Dup Doc")
    children = [c for c in chunks if c.parent_id is not None]
    assert len(children) == 2
    # Same text → same content hash (that's what dedup relies on)
    assert children[0].content_hash == children[1].content_hash

def test_chunker_packs_adjacent_paragraphs():
    """Short paragraphs in the same section are packed into one child until
    the target token size is reached."""
    doc = _make_doc([
        ParsedElement(kind="heading", text="Section", level=1),
        ParsedElement(kind="paragraph", text="First short sentence."),
        ParsedElement(kind="paragraph", text="Second short sentence."),
        ParsedElement(kind="paragraph", text="Third short sentence."),
    ])
    chunks = Chunker().chunk(doc, doc_id="d5", doc_title="Doc")
    children = [c for c in chunks if c.parent_id is not None]
    # All three fit under child_target_tokens → one packed child
    assert len(children) == 1
    assert "First" in children[0].text
    assert "Second" in children[0].text
    assert "Third" in children[0].text

def test_chunker_real_docx_produces_sane_output():
    doc = DocxParser().parse(FIXTURES / "policy_sample.docx")
    chunks = Chunker().chunk(doc, doc_id="d5", doc_title="Policy")
    assert chunks
    parents = [c for c in chunks if c.parent_id is None]
    assert len(parents) >= 1
    # Refund Policy should appear as a section
    assert any("Refund Policy" in (p.section or "") for p in parents)


def test_chunker_real_csv_keeps_table_whole():
    doc = CsvParser().parse(FIXTURES / "sales_sample.csv")
    chunks = Chunker().chunk(doc, doc_id="d6", doc_title="Sales")
    table_children = [c for c in chunks if c.is_table]
    assert len(table_children) >= 1
    # Header row appears in the chunk text
    assert "date" in table_children[0].text.lower()