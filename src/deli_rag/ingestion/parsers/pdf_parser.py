from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import pymupdf as fitz

from .base import ParsedDocument, ParsedElement, ParsedPage, register


@register
class PdfParser:
    name: ClassVar[str] = "pdf"
    supported_mimes: ClassVar[set[str]] = {"application/pdf"}
    supported_extensions: ClassVar[set[str]] = {".pdf"}

    MIN_TEXT_CHARS: ClassVar[int] = 40
    HEADING_SIZE_RATIO: ClassVar[float] = 1.15

    def parse(self, path: Path) -> ParsedDocument:
        doc = fitz.open(path)
        try:
            pages = [self._parse_page(page, i) for i, page in enumerate(doc, start=1)]
            return ParsedDocument(
                source_path=str(path),
                mime="application/pdf",
                pages=pages,
                metadata=dict(doc.metadata or {}),
                parser_name=self.name,
            )
        finally:
            doc.close()

    def _parse_page(self, page: "fitz.Page", number: int) -> ParsedPage:
        text = page.get_text("text").strip()
        if len(text) < self.MIN_TEXT_CHARS:
            ocr = self._try_ocr(page)
            if ocr:
                return ParsedPage(number=number, elements=ocr)

        tables = page.find_tables()
        table_bboxes = [fitz.Rect(t.bbox) for t in tables.tables]

        elements: list[ParsedElement] = []
        for t in tables.tables:
            rows = [[cell or "" for cell in row] for row in t.extract()]
            elements.append(ParsedElement(
                kind="table",
                text="\n".join(" | ".join(c for c in row) for row in rows),
                page=number,
                bbox=tuple(t.bbox),  # type: ignore[arg-type]
                rows=rows,
            ))

        dict_blocks = page.get_text("dict")["blocks"]
        sizes: list[float] = []
        for b in dict_blocks:
            if b.get("type") != 0:
                continue
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        sizes.append(float(span.get("size", 0)))
        body_size = self._mode(sizes) if sizes else 0.0

        for b in dict_blocks:
            if b.get("type") != 0:
                continue
            bbox = fitz.Rect(b["bbox"])
            if any(bbox.intersects(tb) for tb in table_bboxes):
                continue
            parts: list[str] = []
            max_size = 0.0
            for line in b.get("lines", []):
                for span in line.get("spans", []):
                    s = span.get("text", "")
                    if not s.strip():
                        continue
                    parts.append(s)
                    max_size = max(max_size, float(span.get("size", 0)))
            block_text = " ".join(parts).strip()
            if not block_text:
                continue
            kind = "heading" if body_size and max_size >= body_size * self.HEADING_SIZE_RATIO else "paragraph"
            level = None
            if kind == "heading":
                ratio = max_size / body_size if body_size else 1.0
                level = 1 if ratio >= 1.6 else 2 if ratio >= 1.35 else 3
            elements.append(ParsedElement(
                kind=kind, text=block_text, level=level, page=number,
                bbox=(bbox.x0, bbox.y0, bbox.x1, bbox.y1),
            ))

        elements.sort(key=lambda e: (e.page or 0, (e.bbox or (0, 0, 0, 0))[1]))
        return ParsedPage(number=number, elements=elements)

    def _try_ocr(self, page: "fitz.Page") -> list[ParsedElement]:
        try:
            import io
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore

            # EXPLICITLY POINT TO WINDOWS TESSERACT EXECUTABLE
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

        except ImportError:
            return []

        try:
            pix = page.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang="eng").strip()
            if not text:
                return []
            return [ParsedElement(kind="paragraph", text=text,
                                  page=page.number + 1, meta={"ocr": True})]
        except Exception as e:
            print(f"DEBUG: OCR failed: {e}")
            return []

    @staticmethod
    def _mode(values: list[float]) -> float:
        if not values:
            return 0.0
        counts: dict[int, int] = {}
        for v in values:
            counts[round(v)] = counts.get(round(v), 0) + 1
        return float(max(counts.items(), key=lambda kv: kv[1])[0])