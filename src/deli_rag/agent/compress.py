from __future__ import annotations

from dataclasses import dataclass

from deli_rag.config.settings import get_config
from deli_rag.ingestion.tokenizer import count_tokens
from deli_rag.retrieval.types import ScoredChunk


@dataclass
class CompressionReport:
    """What happened during compression. Useful in trace logs and tests."""
    input_count: int
    output_count: int
    duplicates_dropped: int
    low_score_dropped: int
    merged_count: int
    budget_truncated: int
    total_tokens_out: int


def _score(chunk: ScoredChunk) -> float:
    """Best available score: rerank beats rrf beats dense."""
    if chunk.rerank_score is not None:
        return chunk.rerank_score
    if chunk.rrf_score is not None:
        return chunk.rrf_score
    return chunk.dense_score or 0.0


def _chunk_text(c: ScoredChunk) -> str:
    """Text used for token accounting — includes the context line, since
    that's what the prompt will contain."""
    if c.context_line:
        return f"{c.context_line}\n{c.text}"
    return c.text


def compress(chunks: list[ScoredChunk]) -> tuple[list[ScoredChunk], CompressionReport]:
    """Reduce chunks to the smallest useful context.

    Steps:
    1. Sort by best-available score (descending).
    2. Drop exact duplicates by content_hash.
    3. Drop chunks whose score is below config threshold (keep min_chunks_to_keep
       regardless, so we never return nothing).
    4. Optionally merge adjacent same-section chunks when the merge fits under
       max_merged_tokens.
    5. Enforce total token budget; drop the tail until under budget.
    6. Cap to max_chunks.
    """
    cfg = get_config().compression
    report = CompressionReport(
        input_count=len(chunks),
        output_count=0,
        duplicates_dropped=0,
        low_score_dropped=0,
        merged_count=0,
        budget_truncated=0,
        total_tokens_out=0,
    )

    if not chunks:
        return [], report

    # Step 1: sort
    ranked = sorted(chunks, key=_score, reverse=True)

    # Step 2: dedup by content_hash
    if cfg.dedup_by_hash:
        seen: set[str] = set()
        deduped: list[ScoredChunk] = []
        for c in ranked:
            h = c.content_hash if hasattr(c, "content_hash") else None
            # ScoredChunk doesn't have content_hash; use text hash as fallback.
            key = h or _text_hash(c.text)
            if key in seen:
                report.duplicates_dropped += 1
                continue
            seen.add(key)
            deduped.append(c)
        ranked = deduped

    # Step 3: drop low scores, but keep min_chunks_to_keep
    kept: list[ScoredChunk] = []
    for i, c in enumerate(ranked):
        if i < cfg.min_chunks_to_keep or _score(c) >= cfg.min_score:
            kept.append(c)
        else:
            report.low_score_dropped += 1

    # Step 4: merge adjacent same-section chunks
    if cfg.merge_adjacent:
        kept, merged_count = _merge_adjacent(kept, max_tokens=cfg.max_merged_tokens)
        report.merged_count = merged_count

    # Step 5: enforce total token budget
    out: list[ScoredChunk] = []
    total_tokens = 0
    for c in kept:
        t = count_tokens(_chunk_text(c))
        if total_tokens + t <= cfg.max_total_tokens or len(out) < cfg.min_chunks_to_keep:
            out.append(c)
            total_tokens += t
        else:
            report.budget_truncated += 1

    # Step 6: cap to max_chunks
    out = out[: cfg.max_chunks]

    report.output_count = len(out)
    report.total_tokens_out = sum(count_tokens(_chunk_text(c)) for c in out)
    return out, report


# --- helpers ---

def _text_hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _merge_adjacent(
    chunks: list[ScoredChunk], *, max_tokens: int,
) -> tuple[list[ScoredChunk], int]:
    """Merge chunks that are:
    - same doc_id
    - same section (or both None)
    - adjacent pages (page_n, page_{n+1}) or same page
    - total merged tokens <= max_tokens
    Keeps the higher-scored chunk as the merged representative; the merged text
    replaces `.text` on the returned chunk.
    """
    if len(chunks) < 2:
        return chunks, 0

    # Sort by (doc_id, section, page) for adjacency detection
    ordered = sorted(
        chunks,
        key=lambda c: (c.doc_id, c.section or "", c.page or 0, -_score(c)),
    )

    merged: list[ScoredChunk] = []
    merge_count = 0
    i = 0
    while i < len(ordered):
        current = ordered[i]
        j = i + 1
        while j < len(ordered):
            nxt = ordered[j]
            if not _can_merge(current, nxt):
                break
            combined_text = current.text + "\n" + nxt.text
            if count_tokens(combined_text) > max_tokens:
                break
            # Merge: keep current's identity, concatenate text
            current.text = combined_text
            # Ensure the merged chunk carries both source pages for trace
            if nxt.page and (not current.page or nxt.page > current.page):
                current.page = nxt.page
            merge_count += 1
            j += 1
        merged.append(current)
        i = j

    # Re-sort by score for downstream use
    merged.sort(key=_score, reverse=True)
    return merged, merge_count


def _can_merge(a: ScoredChunk, b: ScoredChunk) -> bool:
    if a.doc_id != b.doc_id:
        return False
    # Only merge across *distinct* adjacent pages, and only when both have a section.
    # Same-page chunks are different parts of the same page and should not merge.
    if not a.section or not b.section:
        return False
    if a.section != b.section:
        return False
    pa, pb = a.page, b.page
    if pa is None or pb is None:
        return False
    return abs(pa - pb) == 1