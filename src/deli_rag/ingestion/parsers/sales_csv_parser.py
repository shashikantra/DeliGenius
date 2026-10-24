from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import yaml

from deli_rag.config.settings import get_env

from .base import ParsedDocument, ParsedElement, ParsedPage, TableRecord, register
from .csv_parser import CsvParser


def _load_parser_config() -> dict:
    cfg_path = get_env().config_path.parent / "parsers.yaml"
    if not cfg_path.exists():
        return {}
    return (yaml.safe_load(cfg_path.read_text()) or {}).get("parsers", {})


@register
class SalesCsvParser:
    """Sales history CSV parser.

    Splits rows into:
    - **SKU rows**: have a UPC → real product sales.
    - **Category rows**: empty UPC + Name matches a configured category label
      (e.g. `,Drinks,23,34.26`) → rolled-up totals; tagged with `meta.is_category_total=True`.
    Emits a `sales_rows` TableRecord for the SQL layer.
    """
    name: ClassVar[str] = "sales_csv"
    supported_mimes: ClassVar[set[str]] = {"text/csv"}
    #supported_extensions: ClassVar[set[str]] = {".sales.csv"}
    supported_extensions: ClassVar[set[str]] = {".sales.csv", ".csv"}

    def parse(self, path: Path) -> ParsedDocument:
        cfg = _load_parser_config().get("sales_csv", {})
        category_labels = {c.strip().lower() for c in cfg.get("category_labels", [])}

        base = CsvParser().parse(path)

        # Re-walk raw rows so we can classify
        import csv as _csv
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        cleaned = [ln for ln in raw_lines if ln.strip() and ln.strip() != '" "']
        header_idx = base.metadata.get("header_row_index", 0)

        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = _csv.reader(f)
            rows = [r for i, r in enumerate(reader) if i >= header_idx and any(c.strip() for c in r)]

        header = [c.strip() for c in rows[0]]
        body = rows[1:]

        sku_rows: list[list[str]] = []
        cat_rows: list[list[str]] = []
        for r in body:
            r = [c.strip() for c in r]
            upc = r[0] if r else ""
            # PRIMARY signal: no UPC → category total row.
            # Secondary: name matches a known category label (belt-and-suspenders).
            if not upc:
                cat_rows.append(r)
            else:
                sku_rows.append(r)

        elements: list[ParsedElement] = []
        if sku_rows:
            table_rows = [header] + sku_rows
            elements.append(ParsedElement(
                kind="table",
                text="\n".join(" | ".join(r) for r in table_rows),
                page=1, rows=table_rows,
                caption=f"{path.stem} SKU rows ({len(sku_rows)})",
                meta={"is_category_total": False, "row_count": len(sku_rows)},
            ))
        if cat_rows:
            table_rows = [header] + cat_rows
            elements.append(ParsedElement(
                kind="table",
                text="\n".join(" | ".join(r) for r in table_rows),
                page=1, rows=table_rows,
                caption=f"{path.stem} category totals ({len(cat_rows)})",
                meta={"is_category_total": True, "row_count": len(cat_rows)},
            ))

        records: list[TableRecord] = []
        if sku_rows:
            records.append(TableRecord(
                name="sales_sku_rows", columns=header, rows=sku_rows,
                source_path=str(path), meta={"kind": "sku"},
            ))
        if cat_rows:
            records.append(TableRecord(
                name="sales_category_totals", columns=header, rows=cat_rows,
                source_path=str(path), meta={"kind": "category"},
            ))

        return ParsedDocument(
            source_path=str(path),
            mime="text/csv",
            pages=[ParsedPage(number=1, elements=elements)],
            tables=records,
            metadata={"columns": header,
                      "sku_row_count": len(sku_rows),
                      "category_row_count": len(cat_rows)},
            parser_name=self.name,
        )