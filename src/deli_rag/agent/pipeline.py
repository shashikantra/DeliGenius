from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from deli_rag.agent.compress import CompressionReport, compress
from deli_rag.agent.router import route
from deli_rag.agent.sql_route import SqlEvidence
from deli_rag.embeddings.base import Embedder
from deli_rag.retrieval.hybrid import HybridRetriever
from deli_rag.retrieval.types import ScoredChunk
from deli_rag.reranking.base import Reranker
from deli_rag.schemas import Filters
from deli_rag.schemas.query import TransformedQuery, UnderstoodQuery, Entities

# NEW IMPORT
from deli_rag.agent.text_to_sql import TextToSql


@dataclass
class PipelineResult:
    original_query: str
    understood: object
    transformed: object
    routed: object
    doc_chunks: list[ScoredChunk] = field(default_factory=list)
    sql_evidence: list[SqlEvidence] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)
    compression: CompressionReport | None = None


class Pipeline:
    """Runs understanding → transformation → routing → retrieval → compression
    for one query. Consumed by Asker (Phase 3) and by the Agent (Phase 4)."""

    def __init__(
            self,
            session: Session,
            embedder: Embedder,
            reranker: Reranker | None = None,
    ) -> None:
        self.session = session
        self.embedder = embedder
        self.retriever = HybridRetriever(session, embedder, reranker=reranker)

        # Initialize the Text-to-SQL tool
        self.text_to_sql = TextToSql(session)

    def run(
            self,
            query: str,
            *,
            filters: Filters,
            history: list[tuple[str, str]] | None = None,
            k: int = 8,
    ) -> PipelineResult:
        trace: list[str] = []

        # Fast local intent classification (saves an LLM call)
        q_lower = query.lower()
        if any(w in q_lower for w in ["total", "sum", "average", "how many", "top", "best", "sales", "commission", "stock", "revenue", "sale", "sold"]):
            intent = "fact"
            is_ambig = False
        elif any(w in q_lower for w in ["policy", "how to", "troubleshoot", "why"]):
            intent = "policy"
            is_ambig = False
        else:
            intent = "other"
            is_ambig = False

        # Create a mock understood object so the rest of the pipeline doesn't break
        understood = UnderstoodQuery(
            original=query,
            normalized=q_lower,
            intent=intent,
            entities=Entities(),
            is_ambiguous=is_ambig,
        )
        trace.append(f"understand: intent={understood.intent} "
                     f"ambiguous={understood.is_ambiguous} "
                     f"entities={understood.entities.model_dump()}")
        if understood.is_ambiguous:
            trace.append(f"understand: clarification_needed="
                         f"{understood.clarification_question!r}")

        # Bypass LLM transformation entirely. Just use the raw query.
        transformed = TransformedQuery(
            original=query,
            rewritten=query,
            expanded=query,
            sub_questions=[],
            transformations_applied=["none (bypassed)"]
        )


        trace.append(f"transform: applied={transformed.transformations_applied} "
                     f"subs={len(transformed.sub_questions)} "
                     f"expanded={transformed.expanded[:80]!r}")

        routed = route(understood, transformed)
        for d in routed.decisions:
            trace.append(f"route[{d.sub_question[:50]!r}]: {d.route} "
                         f"kind={d.sql_kind} conf={d.confidence:.2f} "
                         f"reason={d.reason!r}")

        result = PipelineResult(
            original_query=query,
            understood=understood,
            transformed=transformed,
            routed=routed,
            trace=trace,
        )

        if all(d.route == "abstain" for d in routed.decisions):
            trace.append("pipeline: all sub-questions abstained; no retrieval done")
            return result

        # SQL (NEW: Using TextToSql instead of SqlRoute)
        for d in routed.decisions:
            if d.route in ("sql", "both"):
                ev = self.text_to_sql.run(d.sub_question, history=history)
                if ev is None:
                    trace.append("text_to_sql: no evidence or query failed")
                else:
                    result.sql_evidence.append(ev)
                    trace.append(f"text_to_sql: {ev.summary}")

        # Retrieval (only if route is doc_retrieval or both)
        for d in routed.decisions:
            if d.route in ("doc_retrieval", "both"):
                r = self.retriever.search(d.sub_question, filters=filters, k=k)
                trace.append(f"retrieve[{d.sub_question[:50]!r}]: "
                             f"dense={r.dense_candidates} "
                             f"keyword={r.keyword_candidates} "
                             f"fused={r.fused_candidates}")
                result.doc_chunks.extend(r.chunks)

        # Dedup by chunk_id (across sub-questions)
        seen: dict[str, ScoredChunk] = {}
        for c in result.doc_chunks:
            if c.chunk_id not in seen:
                seen[c.chunk_id] = c
            else:
                prev = seen[c.chunk_id]
                if (c.rerank_score or c.rrf_score or 0) > \
                        (prev.rerank_score or prev.rrf_score or 0):
                    seen[c.chunk_id] = c
        pre = list(seen.values())

        # Compression
        compressed, report = compress(pre)
        result.doc_chunks = compressed
        result.compression = report
        trace.append(
            f"compress: in={report.input_count} out={report.output_count} "
            f"dups={report.duplicates_dropped} lowscore={report.low_score_dropped} "
            f"merged={report.merged_count} budget_dropped={report.budget_truncated} "
            f"tokens={report.total_tokens_out}"
        )

        return result