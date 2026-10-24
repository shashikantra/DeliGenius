from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from deli_rag.db.models import ChunkRow, EmbeddingRow
from deli_rag.embeddings.base import Embedder
from deli_rag.ingestion.tokenizer import count_tokens


@dataclass
class IndexReport:
    chunks_scanned: int
    chunks_embedded: int
    chunks_skipped: int
    tokens_estimated: int


class Indexer:
    """Fills the `embeddings` table for chunks that don't have one yet.

    - Idempotent: chunks with an embedding for the current (model_name, model_version)
      are skipped.
    - Batches embedding calls to keep memory bounded.
    - Prepends the chunk's context_line to its text before embedding — this is what
      the chunker prepared for us. The full text (context + body) lives in the
      `chunks.text` column for generation; only the vector sees the concatenation.
    """

    def __init__(self, session: Session, embedder: Embedder, *, batch_size: int = 64) -> None:
        self.session = session
        self.embedder = embedder
        self.batch_size = batch_size

    def index_all(self, *, doc_ids: list[str] | None = None) -> IndexReport:
        """Embed all un-embedded chunks. Optionally restrict to specific doc_ids."""
        query = select(ChunkRow.chunk_id, ChunkRow.text, ChunkRow.context_line)
        query = query.outerjoin(
            EmbeddingRow,
            (EmbeddingRow.chunk_id == ChunkRow.chunk_id)
            & (EmbeddingRow.model_name == self.embedder.name)
            & (EmbeddingRow.model_version == self.embedder.model_version),
        ).where(EmbeddingRow.id.is_(None))
        if doc_ids:
            query = query.where(ChunkRow.doc_id.in_(doc_ids))

        rows = self.session.execute(query).all()
        total = len(rows)
        embedded = 0
        tokens = 0

        for start in range(0, total, self.batch_size):
            batch = rows[start : start + self.batch_size]
            # Prepend context line — same shape the query-time encoder never sees,
            # but the retrieval-time dense matcher benefits from the extra signal.
            payload = [
                (r.context_line + "\n" + r.text).strip() if r.context_line else r.text
                for r in batch
            ]
            tokens += sum(count_tokens(t) for t in payload)
            vectors = self.embedder.embed_documents(payload)
            for r, vec in zip(batch, vectors):
                self.session.add(EmbeddingRow(
                    chunk_id=r.chunk_id,
                    model_name=self.embedder.name,
                    model_version=self.embedder.model_version,
                    vector=vec,
                ))
            self.session.flush()
            embedded += len(batch)

        return IndexReport(
            chunks_scanned=total,
            chunks_embedded=embedded,
            chunks_skipped=0,
            tokens_estimated=tokens,
        )