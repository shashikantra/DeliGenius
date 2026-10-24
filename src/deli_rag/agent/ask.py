from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from deli_rag.agent.llm import GroqClient, LLMReply, parse_json_object
from deli_rag.agent.pipeline import Pipeline, PipelineResult
from deli_rag.agent.prompt import build_prompt
from deli_rag.agent.validate import validate, ValidationReport
from deli_rag.embeddings.base import Embedder
from deli_rag.reranking.base import Reranker
from deli_rag.schemas import Filters
from deli_rag.schemas.answer import Answer, Citation

log = logging.getLogger(__name__)


@dataclass
class AskResult:
    question: str
    answer: Answer
    citations: list[Citation] = field(default_factory=list)
    validation: ValidationReport | None = None
    pipeline: PipelineResult | None = None
    llm: LLMReply | None = None


class Asker:
    """End-to-end: pipeline → prompt → Groq → parse → validate → AskResult."""

    def __init__(
            self,
            session: Session,
            embedder: Embedder,
            reranker: Reranker | None = None,
            groq: GroqClient | None = None,
    ) -> None:
        self.pipeline = Pipeline(session, embedder, reranker=reranker)
        self.groq = groq or GroqClient()

    def ask(
            self,
            question: str,
            *,
            filters: Filters,
            history: list[tuple[str, str]] | None = None,
            k: int = 8,
            prefer_local: bool = False,  # <--- ADDED THIS
    ) -> AskResult:
        pipe_result = self.pipeline.run(question, filters=filters, history=history, k=k)
        # ==========================================
        # DIRECT ANSWER: If SQL found data, trust it.
        # ==========================================
        if pipe_result.sql_evidence:
            ev = pipe_result.sql_evidence[0]

            print(f"🔴 [DEBUG] SQL Evidence found:")
            print(f"🔴 [DEBUG]   kind: {ev.kind}")
            print(f"🔴 [DEBUG]   summary: {ev.summary}")
            print(f"🔴 [DEBUG]   rows: {ev.rows}")
            print(f"🔴 [DEBUG]   sql: {ev.sql}")

            # If the SQL query returned a valid data row (not just "No records found")
            if ev.rows and ev.rows[0] and "no matching" not in str(ev.rows[0][0]).lower():
                answer = Answer(
                    answer=ev.summary,
                    citations=[1],
                    confidence=0.99,
                    abstained=False,
                    reason=""
                )
                citations = [Citation(
                    id=1, kind="sql",
                    sql_kind=ev.kind,
                    sql_summary=ev.summary,
                    sql_query=ev.sql,
                    sql_data=ev.rows,
                )]
                return AskResult(
                    question=question,
                    answer=answer,
                    citations=citations,
                    pipeline=pipe_result
                )
        print(f"🟠 [ASKER] ask() called with prefer_local={prefer_local}")  # <--- ADD

        if not pipe_result.doc_chunks and not pipe_result.sql_evidence:
            answer = Answer(
                answer="",
                citations=[],
                confidence=0.0,
                abstained=True,
                reason="I could not find data for that question. Please try rephrasing it or specifying a date.",
            )
            return AskResult(question=question, answer=answer, pipeline=pipe_result)

        print(f"🟠 [ASKER] Evidence count: sql={len(pipe_result.sql_evidence)} doc={len(pipe_result.doc_chunks)}")  # <--- ADD

        system, user, evidence_index = build_prompt(
            question, pipe_result.doc_chunks, pipe_result.sql_evidence,
        )

        print(f"🟠 [ASKER] Calling LLM with prefer_local={prefer_local}")  # <--- ADD
        reply = self.groq.complete_json(system=system, user=user, prefer_local=prefer_local)  # <--- ADDED prefer_local
        print(f"🟢 [ASKER] LLM returned: {reply.content[:100]}...")  # <--- ADD

        try:
            raw = parse_json_object(reply.content)
        except Exception as e:
            answer = Answer(
                answer="", citations=[], confidence=0.0, abstained=True,
                reason=f"LLM returned non-JSON: {e}",
            )
            return AskResult(
                question=question, answer=answer,
                pipeline=pipe_result, llm=reply,
            )

        try:
            answer = Answer.model_validate(raw)
        except Exception as e:
            answer = Answer(
                answer="", citations=[], confidence=0.0, abstained=True,
                reason=f"LLM JSON did not match schema: {e}",
            )
            return AskResult(
                question=question, answer=answer,
                pipeline=pipe_result, llm=reply,
            )

        report = None

        citations: list[Citation] = []
        for cid in answer.citations:
            meta = next((e for e in evidence_index if int(e["id"]) == cid), None)
            if not meta:
                continue
            if meta["kind"] == "doc":
                citations.append(Citation(
                    id=cid, kind="doc",
                    chunk_id=meta.get("chunk_id"),
                    filename=meta.get("filename"),
                    page=meta.get("page"),
                    section=meta.get("section"),
                ))
            else:
                citations.append(Citation(
                    id=cid, kind="sql",
                    sql_kind=meta.get("sql_kind"),
                    sql_summary=meta.get("sql_summary"),
                    sql_query=meta.get("sql_query"),
                    sql_data=meta.get("sql_data"),
                ))

        return AskResult(
            question=question,
            answer=answer,
            citations=citations,
            validation=report,
            pipeline=pipe_result,
            llm=reply,
        )