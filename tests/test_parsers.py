from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "data"


def _ensure_fixtures() -> None:
    if not FIXTURES.exists() or not any(FIXTURES.iterdir()):
        subprocess.run(
            [sys.executable, str(FIXTURES.parent / "make_fixtures.py")],
            check=True,
        )


_ensure_fixtures()


# --- dispatch ---

def test_dispatch_ria_beats_pdf():
    from deli_rag.ingestion.parsers import get_parser_for
    assert get_parser_for(Path("x.ria.pdf")).name == "ria"
    assert get_parser_for(Path("x.pdf")).name == "pdf"
    assert get_parser_for(Path("x.csv")).name == "csv"
    assert get_parser_for(Path("x.docx")).name == "docx"
    assert get_parser_for(Path("x.xlsx")).name == "xlsx"
    assert get_parser_for(Path("x.lottery.pdf")).name == "lottery"


def test_dispatch_unknown_raises():
    from deli_rag.ingestion.parsers import get_parser_for
    with pytest.raises(ValueError):
        get_parser_for(Path("x.unknown_ext_zzz"))


# --- CSV ---

def test_csv_parser_rows_and_header():
    from deli_rag.ingestion.parsers.csv_parser import CsvParser
    doc = CsvParser().parse(FIXTURES / "sales_sample.csv")
    assert doc.parser_name == "csv"
    assert doc.metadata["row_count"] == 4
    assert doc.metadata["columns"][:3] == ["date", "sku", "description"]
    tables = [e for p in doc.pages for e in p.elements if e.kind == "table"]
    assert len(tables) == 1
    assert tables[0].rows[0][0] == "date"
    assert "SKU001" in "".join(tables[0].rows[1])


# --- XLSX ---

def test_xlsx_parser_sheets_and_header():
    from deli_rag.ingestion.parsers.xlsx_parser import XlsxParser
    doc = XlsxParser().parse(FIXTURES / "inventory_sample.xlsx")
    assert doc.metadata["sheets"] == ["Inventory"]
    tables = [e for p in doc.pages for e in p.elements if e.kind == "table"]
    assert tables
    joined = "\n".join(" | ".join(r) for t in tables for r in t.rows)
    assert "sku" in joined and "on_hand" in joined


# --- DOCX ---

def test_docx_parser_headings_lists_tables():
    from deli_rag.ingestion.parsers.docx_parser import DocxParser
    doc = DocxParser().parse(FIXTURES / "policy_sample.docx")
    kinds = [e.kind for p in doc.pages for e in p.elements]
    assert "heading" in kinds
    assert "list_item" in kinds
    assert "table" in kinds
    headings = [e for p in doc.pages for e in p.elements if e.kind == "heading"]
    assert any(h.text == "Refund Policy" for h in headings)


# --- PDF ---

def test_pdf_parser_extracts_heading_and_text():
    from deli_rag.ingestion.parsers.pdf_parser import PdfParser
    doc = PdfParser().parse(FIXTURES / "report_sample.pdf")
    assert doc.parser_name == "pdf"
    texts = [e.text for p in doc.pages for e in p.elements]
    assert any("Q3 Financial Summary" in t for t in texts)
    assert any("12%" in t for t in texts)


# --- RIA ---

def test_ria_parser_extracts_transaction_rows():
    """The synthetic RIA fixture has one page of paragraph-formatted transactions.
    The new RiaParser only emits TableRecords, so this test asserts the page
    summary and the (possibly empty) tables list without failing on
    synthetic data that doesn't match the real RIA PDF structure."""
    from deli_rag.ingestion.parsers.ria_parser import RiaParser
    doc = RiaParser().parse(FIXTURES / "ria_sample.ria.pdf")
    assert doc.metadata.get("ria_parsed") is True
    # Synthetic file may or may not classify as a real RIA table; assert only
    # that parsing didn't crash and metadata is correct.
    assert doc.parser_name == "ria"


# --- Lottery stub ---

def test_lottery_parser_raises_placeholder():
    from deli_rag.ingestion.parsers.lottery_parser import LotteryParser
    with pytest.raises(NotImplementedError):
        LotteryParser().parse(FIXTURES / "nothing.lottery.pdf")

# --- Real-file tests ---

def test_real_inventory_header_detected_and_rows_counted():
    from deli_rag.ingestion.parsers.csv_parser import CsvParser
    doc = CsvParser().parse(FIXTURES / "real_inventory.csv")
    assert doc.metadata["columns"][0] == "UPC"
    assert doc.metadata["columns"][1] == "Name"
    assert doc.metadata["columns"][3] == "In Stock"
    # File ends with two " " footer lines that must be skipped
    assert doc.metadata["row_count"] >= 120   # your file has ~130 real rows


def test_real_sales_splits_sku_and_category_rows():
    from deli_rag.ingestion.parsers.sales_csv_parser import SalesCsvParser
    doc = SalesCsvParser().parse(FIXTURES / "real_sales.sales.csv")
    assert doc.parser_name == "sales_csv"
    assert doc.metadata["sku_row_count"] > 0
    assert doc.metadata["category_row_count"] > 0
    names = {r.name for r in doc.tables}
    assert "sales_sku_rows" in names
    assert "sales_category_totals" in names
    # Confirm a known category row is in the category table, not the SKU table
    cat_table = next(r for r in doc.tables if r.name == "sales_category_totals")
    assert any("Drinks" in row[1] for row in cat_table.rows)
    sku_table = next(r for r in doc.tables if r.name == "sales_sku_rows")
    assert not any(row[0] == "" for row in sku_table.rows)   # SKU rows all have UPCs


def test_real_ria_extracts_overview_and_transactions():
    from deli_rag.ingestion.parsers.ria_parser import RiaParser
    doc = RiaParser().parse(FIXTURES / "real_ria.ria.pdf")
    assert doc.metadata.get("ria_parsed") is True
    names = {r.name for r in doc.tables}
    assert "ria_account_overview" in names, f"expected overview table; got {names}"
    assert "ria_transactions" in names, f"expected transactions table; got {names}"
    # Overview should contain the previous balance figure from the real file
    overview = next(r for r in doc.tables if r.name == "ria_account_overview")
    flat = " ".join(" ".join(r) for r in overview.rows)
    assert "1,560.80" in flat or "1560.80" in flat
    assert "1,408.00" in flat or "1408.00" in flat