from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from deli_rag.config.settings import get_config
from deli_rag.ingestion.parsers.base import (
    ParsedDocument, ParsedElement, ParsedPage,
)
from deli_rag.ingestion.tokenizer import count_tokens


@dataclass
class DraftChunk:
    chunk_id: str
    parent_id: str | None
    page: int | None
    section: str | None
    text: str
    context_line: str
    token_count: int
    is_table: bool
    table_summary: str | None
    content_hash: str


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _new_id() -> str:
    return uuid.uuid4().hex[:24]


class Chunker:
    """Turns a ParsedDocument into parent/child chunks.

    Section boundaries are heading elements (level 1..3). Tables are emitted
    as their own child chunks with the caption preserved. Paragraphs and
    list items within a section are packed into children up to
    `child_target_tokens`, with `overlap_tokens` of trailing overlap.
    """

    def __init__(self) -> None:
        self.cfg = get_config().chunking

    def chunk(self, doc: ParsedDocument, *, doc_id: str, doc_title: str) -> list[DraftChunk]:
        out: list[DraftChunk] = []
        section_stack: list[tuple[int, str]] = []   # (level, heading_text)
        section_elements: list[ParsedElement] = []

        def flush_section() -> None:
            if not section_elements:
                return
            section_title = self._section_breadcrumb(section_stack)
            parent_id = _new_id()
            parent_text = self._render_section_text(section_elements)
            out.append(DraftChunk(
                chunk_id=parent_id,
                parent_id=None,
                page=section_elements[0].page,
                section=section_title,
                text=parent_text,
                context_line=self._context_line(doc_title, section_title),
                token_count=count_tokens(parent_text),
                is_table=False,
                table_summary=None,
                content_hash=_hash(parent_text),
            ))
            out.extend(self._children_of(
                parent_id=parent_id,
                elements=section_elements,
                doc_title=doc_title,
                section_title=section_title,
            ))
            section_elements.clear()

        for page in doc.pages:
            for el in page.elements:
                if el.kind == "heading":
                    flush_section()
                    level = el.level or 1
                    while section_stack and section_stack[-1][0] >= level:
                        section_stack.pop()
                    section_stack.append((level, el.text.strip()))
                    continue
                section_elements.append(el)
        flush_section()
        return out

    # --- internals ---

    def _children_of(
        self,
        *,
        parent_id: str,
        elements: list[ParsedElement],
        doc_title: str,
        section_title: str,
    ) -> list[DraftChunk]:
        children: list[DraftChunk] = []

        # 1) Emit each table as its own child. If it's too big, split it into smaller chunks.
        prose: list[ParsedElement] = []
        for el in elements:
            if el.kind == "table" and el.rows:
                # Split tables that are too large (e.g., > 25 rows)
                if len(el.rows) > 25:
                    header = el.rows[0]
                    body = el.rows[1:]
                    for i in range(0, len(body), 20):
                        batch = body[i:i+20]
                        # Re-create a smaller table element
                        small_el = ParsedElement(
                            kind="table",
                            text="\n".join(" | ".join(r) for r in [header] + batch),
                            page=el.page,
                            rows=[header] + batch,
                            caption=el.caption,
                        )
                        children.append(self._table_child(
                            parent_id=parent_id, el=small_el,
                            doc_title=doc_title, section_title=section_title,
                        ))
                else:
                    children.append(self._table_child(
                        parent_id=parent_id, el=el,
                        doc_title=doc_title, section_title=section_title,
                    ))
            else:
                prose.append(el)

        # 2) Pack prose into children of target size.
        if not prose:
            return children

        buf: list[ParsedElement] = []
        buf_tokens = 0

        def flush_buf() -> None:
            nonlocal buf, buf_tokens
            if not buf:
                return
            text = self._render_section_text(buf)
            children.append(DraftChunk(
                chunk_id=_new_id(),
                parent_id=parent_id,
                page=buf[0].page,
                section=section_title,
                text=text,
                context_line=self._context_line(doc_title, section_title),
                token_count=count_tokens(text),
                is_table=False,
                table_summary=None,
                content_hash=_hash(text),
            ))
            # Light overlap: keep the last element if it fits under the overlap budget.
            tail = buf[-1:]
            tail_tokens = count_tokens(self._render_section_text(tail)) if tail else 0
            if tail and tail_tokens <= self.cfg.overlap_tokens:
                buf = tail
                buf_tokens = tail_tokens
            else:
                buf = []
                buf_tokens = 0

        for el in prose:
            el_tokens = count_tokens(el.text)
            # Single oversized paragraph: hard-split by tokens.
            if el_tokens > self.cfg.child_max_tokens:
                if buf:
                    flush_buf()
                children.extend(self._split_oversized(
                    parent_id=parent_id, el=el,
                    doc_title=doc_title, section_title=section_title,
                ))
                continue
            # Would this overflow the target?
            if buf and (buf_tokens + el_tokens > self.cfg.child_target_tokens):
                flush_buf()
            buf.append(el)
            buf_tokens += el_tokens
        flush_buf()
        return children

    def _split_oversized(
        self, *, parent_id: str, el: ParsedElement,
        doc_title: str, section_title: str,
    ) -> list[DraftChunk]:
        """Split an oversized element by sentences, then by hard token windows."""
        sentences = self._split_sentences(el.text)
        out: list[DraftChunk] = []
        buf: list[str] = []
        buf_tokens = 0
        for s in sentences:
            st = count_tokens(s)
            if buf and buf_tokens + st > self.cfg.child_target_tokens:
                text = " ".join(buf)
                out.append(self._simple_child(
                    parent_id, text, el.page, section_title, doc_title,
                ))
                buf = []
                buf_tokens = 0
            buf.append(s)
            buf_tokens += st
        if buf:
            out.append(self._simple_child(
                parent_id, " ".join(buf), el.page, section_title, doc_title,
            ))
        return out

    def _table_child(
        self, *, parent_id: str, el: ParsedElement,
        doc_title: str, section_title: str,
    ) -> DraftChunk:
        text = el.text
        if el.caption:
            text = f"{el.caption}\n{text}"
        summary = self._table_summary(el)
        return DraftChunk(
            chunk_id=_new_id(),
            parent_id=parent_id,
            page=el.page,
            section=section_title,
            text=text,
            context_line=self._context_line(doc_title, section_title),
            token_count=count_tokens(text),
            is_table=True,
            table_summary=summary,
            content_hash=_hash(text),
        )

    def _simple_child(
        self, parent_id: str, text: str, page: int | None,
        section_title: str, doc_title: str,
    ) -> DraftChunk:
        return DraftChunk(
            chunk_id=_new_id(),
            parent_id=parent_id,
            page=page,
            section=section_title,
            text=text,
            context_line=self._context_line(doc_title, section_title),
            token_count=count_tokens(text),
            is_table=False,
            table_summary=None,
            content_hash=_hash(text),
        )

    def _render_section_text(self, elements: list[ParsedElement]) -> str:
        parts: list[str] = []
        for el in elements:
            if el.kind == "list_item":
                parts.append(f"- {el.text}")
            elif el.kind == "heading":
                parts.append(el.text)
            else:
                parts.append(el.text)
        return "\n".join(parts)

    def _section_breadcrumb(self, stack: list[tuple[int, str]]) -> str:
        return " > ".join(t for _, t in stack) if stack else "(untitled)"

    def _context_line(self, doc_title: str, section: str) -> str:
        line = f"{doc_title} — {section}"
        if count_tokens(line) <= self.cfg.context_line_max_tokens:
            return line
        # Trim from the left until under limit.
        while count_tokens(line) > self.cfg.context_line_max_tokens and " — " in line:
            line = line.split(" — ", 1)[1]
        return line

    def _table_summary(self, el: ParsedElement) -> str:
        rows = el.rows or []
        if not rows:
            return ""
        header = rows[0]
        n = len(rows) - 1
        return f"{n} rows, columns: {', '.join(h or '?' for h in header)}"

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        import re
        # Cheap sentence splitter; good enough for chunking.
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
        return [p.strip() for p in parts if p.strip()]