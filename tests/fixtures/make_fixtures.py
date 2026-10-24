"""Generate SYNTHETIC test fixtures so parser tests can run today.

Replace with real (redacted) files once available. Every generated file is
clearly tagged as synthetic in its own content.
"""
from __future__ import annotations

from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "data"


def make_csv() -> Path:
    p = FIXTURE_DIR / "sales_sample.csv"
    p.write_text(
        "# SYNTHETIC - replace with real export\n"
        "date,sku,description,qty,unit_price,total\n"
        "2026-10-01,SKU001,Whole milk 1gal,12,4.29,51.48\n"
        "2026-10-01,SKU002,Sourdough loaf,8,5.99,47.92\n"
        "2026-10-02,SKU001,Whole milk 1gal,15,4.29,64.35\n"
        "2026-10-02,SKU003,American cheese lb,6,6.49,38.94\n",
        encoding="utf-8",
    )
    return p


def make_xlsx() -> Path:
    from openpyxl import Workbook
    p = FIXTURE_DIR / "inventory_sample.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventory"
    ws.append(["sku", "description", "on_hand", "reorder_point"])
    for row in [
        ("SKU001", "Whole milk 1gal", 42, 24),
        ("SKU002", "Sourdough loaf", 18, 12),
        ("SKU003", "American cheese lb", 7, 10),
    ]:
        ws.append(row)
    wb.save(p)
    return p


def make_docx() -> Path:
    from docx import Document
    p = FIXTURE_DIR / "policy_sample.docx"
    doc = Document()
    doc.add_heading("Refund Policy", level=1)
    doc.add_paragraph("Refunds are accepted within 30 days with a receipt.")
    doc.add_paragraph("Manager approval required for refunds over $50.",
                      style="List Bullet")
    doc.add_heading("Store Hours", level=2)
    doc.add_paragraph("Monday to Saturday 7am-9pm. Sunday 8am-6pm.")
    tbl = doc.add_table(rows=2, cols=3)
    hdr = tbl.rows[0].cells
    hdr[0].text, hdr[1].text, hdr[2].text = "Day", "Open", "Close"
    r = tbl.rows[1].cells
    r[0].text, r[1].text, r[2].text = "Mon-Sat", "07:00", "21:00"
    doc.save(p)
    return p


def make_pdf() -> Path:
    import pymupdf as fitz
    p = FIXTURE_DIR / "report_sample.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 110), "Q3 Financial Summary", fontsize=20)
    page.insert_text((72, 150), "Revenue grew 12% quarter over quarter.", fontsize=11)
    page.insert_text((72, 170), "Operating margin held steady at 8.4%.", fontsize=11)
    for i, row in enumerate([["Metric", "Q2", "Q3"],
                             ["Revenue", "1,200,000", "1,344,000"],
                             ["Margin", "8.1%", "8.4%"]]):
        for j, cell in enumerate(row):
            page.insert_text((72 + j * 120, 220 + i * 18), cell, fontsize=10)
    doc.save(p)
    doc.close()
    return p


def make_ria_pdf() -> Path:
    import pymupdf as fitz
    p = FIXTURE_DIR / "ria_sample.ria.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 110), "RIA Money Transfer - Daily Activity", fontsize=16)
    page.insert_text((72, 150), "Date       Reference      Amount     Agent",
                     fontsize=11)
    rows = [
        "10/14/2026 RIA000123456 $1,250.00  Brooklyn Main",
        "10/14/2026 RIA000123457   $430.50  Queens Blvd",
        "10/15/2026 RIA000123458   $980.00  Bronx Hub",
    ]
    for i, r in enumerate(rows):
        page.insert_text((72, 170 + i * 16), r, fontsize=10)
    doc.save(p)
    doc.close()
    return p


def main() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for fn in (make_csv, make_xlsx, make_docx, make_pdf, make_ria_pdf):
        print(fn())


if __name__ == "__main__":
    main()