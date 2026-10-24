from __future__ import annotations

import csv
from pathlib import Path
from typing import ClassVar

import yaml

from deli_rag.config.settings import get_env

from .base import ParsedDocument, ParsedElement, ParsedPage, TableRecord, register


def _load_parser_config() -> dict:
    cfg_path = get_env().config_path.parent / "parsers.yaml"
    if not cfg_path.exists():
        return {}
    return (yaml.safe_load(cfg_path.read_text()) or {}).get("parsers", {})


@register
class CsvParser:
    """CSV parser with header auto-detection.

    - Skips blank lines, whitespace-only lines, and lines that are just `" "`.
    - Finds the header row by matching keywords (UPC, Name, Qty, etc.).
      Override per filename in `config/parsers.yaml` under `csv.skip_rows_overrides`.
    - Emits row-group table elements with the header repeated (for RAG chunks).
    - Emits one TableRecord with the full dataset (for the Track-2 SQL loaders).
    """
    name: ClassVar[str] = "csv"
    supported_mimes: ClassVar[set[str]] = {"text/csv", "application/csv"}
    supported_extensions: ClassVar[set[str]] = {".csv"}

    ROWS_PER_GROUP: ClassVar[int] = 200

    def parse(self, path: Path) -> ParsedDocument:
        cfg = _load_parser_config().get("csv", {})
        keywords = [k.lower() for k in cfg.get("header_keywords", [])]
        min_matches = int(cfg.get("min_keyword_matches", 2))
        overrides = cfg.get("skip_rows_overrides", {}) or {}

        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        # Filter out blank and quoted-space-only lines
        cleaned = [ln for ln in raw_lines if ln.strip() and ln.strip() != '" "']

        explicit_skip = overrides.get(path.name)
        if explicit_skip is not None:
            header_idx = int(explicit_skip)
        else:
            header_idx = self._detect_header_row(cleaned, keywords, min_matches)

        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            rows: list[list[str]] = []
            for i, row in enumerate(reader):
                if i < header_idx:
                    continue
                if not any(c.strip() for c in row):
                    continue
                if len(row) == 1 and row[0].strip() in ("", '" "', " "):
                    continue
                rows.append([c.strip() for c in row])

        if not rows:
            return ParsedDocument(
                source_path=str(path),
                mime="text/csv",
                pages=[ParsedPage(number=1, elements=[])],
                metadata={"row_count": 0},
                parser_name=self.name,
            )

        header = rows[0]
        body = rows[1:]

        elements: list[ParsedElement] = []
        total = len(body)
        for start in range(0, total, self.ROWS_PER_GROUP):
            group = body[start: start + self.ROWS_PER_GROUP]
            table_rows = [header] + group

            # Build a valid Markdown table for ReactMarkdown to render
            md_rows = []
            md_rows.append("| " + " | ".join(header) + " |")
            md_rows.append("| " + " | ".join(["---"] * len(header)) + " |")
            for r in group:
                md_rows.append("| " + " | ".join(r) + " |")

            elements.append(ParsedElement(
                kind="table",
                text="\n".join(md_rows),
                page=1,
                rows=table_rows,
                caption=f"{path.stem} rows {start + 1}-{start + len(group)}",
                meta={"row_start": start + 1,
                      "row_end": start + len(group),
                      "row_count": total,
                      "header_repeated": True},
            ))

        # TableRecord: the full unpaginated table for the Track-2 SQL loaders.
        records: list[TableRecord] = [TableRecord(
            name="csv_table",
            columns=header,
            rows=body,
            source_path=str(path),
            meta={"row_count": total, "header_row_index": header_idx},
        )]

        return ParsedDocument(
            source_path=str(path),
            mime="text/csv",
            pages=[ParsedPage(number=1, elements=elements)],
            tables=records,
            metadata={"columns": header, "row_count": total,
                      "header_row_index": header_idx},
            parser_name=self.name,
        )

    @staticmethod
    def _detect_header_row(lines: list[str], keywords: list[str], min_matches: int) -> int:
        """Return the index of the first line that looks like a header row.
        Falls back to 0 if nothing matches."""
        if not keywords:
            return 0
        for idx, line in enumerate(lines[:20]):   # only scan the top of the file
            try:
                cells = next(csv.reader([line]))
            except Exception:
                continue
            lowered = [c.strip().lower() for c in cells]
            matches = sum(1 for c in lowered if any(k in c for k in keywords))
            if matches >= min_matches:
                return idx
        return 0