"""Throwaway diagnostic — inspect what RiaParser sees in the real RIA PDF."""
import json
from collections import Counter
from pathlib import Path

from deli_rag.ingestion.parsers.ria_parser import RiaParser
from deli_rag.ingestion.parsers.pdf_parser import PdfParser

path = Path("tests/fixtures/data/real_ria.ria.pdf")

# Step 1: what does the raw PDF parser see?
pdf = PdfParser().parse(path)
kinds = Counter(e.kind for p in pdf.pages for e in p.elements)
print("=== PdfParser element kinds ===")
print(kinds)

# Step 2: show any element that mentions Account Overview
print("\n=== Elements mentioning RIA keywords ===")
for p in pdf.pages:
    for e in p.elements:
        if any(k in e.text for k in ["Previous Balance", "MT Send", "Account Overview", "Total Balance"]):
            print(f"[page {e.page}] kind={e.kind!r}")
            print(f"  text[:300]: {e.text[:300].replace(chr(10), ' / ')}")
            if e.rows:
                print(f"  rows (first 3): {e.rows[:3]}")

# Step 3: what does RiaParser emit?
ria = RiaParser().parse(path)
print("\n=== RiaParser TableRecords ===")
for t in ria.tables:
    print(f"- {t.name}: cols={t.columns}")
    print(f"  first row: {t.rows[0] if t.rows else '(none)'}")