from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from .base import ParsedDocument, ParsedElement, ParsedPage, TableRecord, register
from .pdf_parser import PdfParser


# Line patterns for the Account Overview block (which PyMuPDF returns as paragraphs).
# Each line looks like "Previous Balance as of 06/21/2026 1,560.80 0.00 1,560.80"
# or "MT Send 1,408.00 0.00 1,408.00" — label + up to 3 numbers.
_OVERVIEW_LINE_RE = re.compile(
    r"^\s*(?P<label>"
    r"Previous Balance(?:\s+as\s+of\s+[\d/]+)?"
    r"|MT Send"
    r"|ACH"
    r"|Total Balance"
    r"|Amount to Pay"
    r"|Amount of Last Deposit"
    r"|Date of Last Deposit"
    r"|Deposited to"
    r"|Settlement Days"
    r"|Report Time"
    r"|Currency"
    r")\s*:?\s*(?P<rest>.*)$",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(r"-?\d[\d,]*\.\d{2}|-?\d[\d,]+")


@register
class RiaParser:
    """RIA money-transfer statement parser.

    Real statement layout (confirmed against the Dandelion/Ria sample):
    - **Account Overview** comes through PyMuPDF as separate paragraphs, not a table.
      We assemble it into `ria_account_overview` by matching label lines.
    - **Branch summary** appears as a table with a `Branch` column → `ria_branch_summary`.
    - **Detail transactions** appear as a table with `Ref No` + `Description` → `ria_transactions`.
    """
    name: ClassVar[str] = "ria"
    supported_mimes: ClassVar[set[str]] = {"application/pdf"}
    #supported_extensions: ClassVar[set[str]] = {".ria.pdf"}
    supported_extensions: ClassVar[set[str]] = {".ria.pdf", ".pdf"}

    def parse(self, path: Path) -> ParsedDocument:
        pdf = PdfParser().parse(path)

        overview_rows: list[list[str]] = []
        records: list[TableRecord] = []
        out_pages: list[ParsedPage] = []

        for page in pdf.pages:
            new_elements: list[ParsedElement] = []
            page_overview: list[list[str]] = []

            for el in page.elements:
                if el.kind == "paragraph":
                    line = self._extract_overview_line(el.text)
                    if line is not None:
                        page_overview.append(line)
                    new_elements.append(el)

                elif el.kind == "table" and el.rows:
                    kind = self._classify_table(el.rows)

                    # Find the real header row (PyMuPDF sometimes inserts a blank leading row)
                    real_header_idx = 0
                    for i, r in enumerate(el.rows[:3]):
                        if any(c.strip() for c in r):
                            real_header_idx = i
                            break
                    header = el.rows[real_header_idx]
                    body = el.rows[real_header_idx + 1:]

                    print(f"DEBUG: RIA Table found. Classified as: {kind}")
                    print(f"DEBUG: Header row: {header}")

                    if kind == "detail":
                        records.append(TableRecord(
                            name="ria_transactions",
                            columns=header,
                            rows=body,
                            page=el.page,
                            source_path=str(path),
                            meta={"ria_kind": "detail"},
                        ))
                    elif kind == "branch":
                        records.append(TableRecord(
                            name="ria_branch_summary",
                            columns=header,
                            rows=body,
                            page=el.page,
                            source_path=str(path),
                            meta={"ria_kind": "branch"},
                        ))
                    new_elements.append(el)

                else:
                    new_elements.append(el)

            if page_overview:
                overview_rows.extend(page_overview)
            out_pages.append(ParsedPage(number=page.number, elements=new_elements))

        if overview_rows:
            records.insert(0, TableRecord(
                name="ria_account_overview",
                columns=["label", "value", "value2", "value3"],
                rows=overview_rows,
                page=1,
                source_path=str(path),
                meta={"ria_kind": "overview"},
            ))

        return ParsedDocument(
            source_path=str(path),
            mime="application/pdf",
            pages=out_pages,
            tables=records,
            metadata={**pdf.metadata, "ria_parsed": True},
            parser_name=self.name,
        )

    @staticmethod
    def _extract_overview_line(text: str) -> list[str] | None:
        """Match a line like 'Previous Balance as of 06/21/2026 1,560.80 0.00 1,560.80'.
        Returns [label, value1, value2, value3] or None."""
        m = _OVERVIEW_LINE_RE.match(text.strip())
        if not m:
            return None
        label = m.group("label").strip()
        rest = m.group("rest").strip()
        nums = _NUMBER_RE.findall(rest)
        row = [label] + (nums[:3] + [""] * 3)[:3]
        return row

    @staticmethod
    def _classify_table(rows: list[list[str]]) -> str:
        if not rows:
            return "other"

        # Scan the first 3 rows to find a header
        candidates: list[str] = []
        for r in rows[:3]:
            joined = " ".join(c.lower() for c in r if c).strip()
            if joined:
                candidates.append(joined)

        header = " | ".join(candidates)

        # Normalize by removing punctuation like "." and "," (helps with OCR noise)
        import re
        normalized_header = re.sub(r'[^a-z0-9\s]', '', header)

        # Check for the key column names
        has_ref = "ref no" in normalized_header or "ref  no" in normalized_header
        has_desc = "description" in normalized_header
        has_branch = "branch" in normalized_header
        has_trnx = "trnx" in normalized_header or "trx" in normalized_header

        if has_ref and has_desc:
            return "detail"
        if has_branch and has_trnx:
            return "branch"
        if has_ref:
            return "detail"

        return "other"