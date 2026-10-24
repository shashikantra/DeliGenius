from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from docx import Document

from .base import ParsedDocument, ParsedElement, ParsedPage, register


@register
class DocxParser:
    name: ClassVar[str] = "docx"
    supported_mimes: ClassVar[set[str]] = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    supported_extensions: ClassVar[set[str]] = {".docx"}

    def parse(self, path: Path) -> ParsedDocument:
        doc = Document(str(path))
        elements: list[ParsedElement] = []

        for item in doc.iter_inner_content():
            cls_name = item.__class__.__name__
            if cls_name == "Paragraph":
                text = item.text.strip()
                if not text:
                    continue
                style = (item.style.name or "").lower() if item.style else ""
                level: int | None = None
                kind = "paragraph"
                if style.startswith("heading"):
                    kind = "heading"
                    tail = style.replace("heading", "").strip()
                    level = int(tail) if tail.isdigit() else 1
                elif style == "title":
                    kind = "heading"; level = 1
                elif style.startswith("list"):
                    kind = "list_item"; level = 1
                elements.append(ParsedElement(kind=kind, text=text, level=level, page=1))
            elif cls_name == "Table":
                rows = [[cell.text.strip() for cell in row.cells] for row in item.rows]
                elements.append(ParsedElement(
                    kind="table",
                    text="\n".join(" | ".join(r) for r in rows),
                    page=1, rows=rows,
                ))

        core = doc.core_properties
        metadata = {
            "title": core.title or "",
            "author": core.author or "",
            "created": core.created.isoformat() if core.created else None,
        }
        return ParsedDocument(
            source_path=str(path),
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            pages=[ParsedPage(number=1, elements=elements)],
            metadata=metadata,
            parser_name=self.name,
        )