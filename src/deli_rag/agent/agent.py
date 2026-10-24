from __future__ import annotations

import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from deli_rag.agent.ask import AskResult, Asker
from deli_rag.agent.sufficiency import SufficiencyReport, check as sufficiency_check
from deli_rag.config.settings import get_config
from deli_rag.embeddings.base import Embedder
from deli_rag.reranking.base import Reranker
from deli_rag.schemas import Filters


@dataclass
class Attempt:
    iteration: int
    k_used: int
    suff: SufficiencyReport
    answer_confidence: float
    abstained: bool
    note: str = ""


@dataclass
class AgentResult:
    question: str
    final: AskResult
    attempts: list[Attempt] = field(default_factory=list)
    iterations_used: int = 0
    gave_up_reason: str = ""
    elapsed_s: float = 0.0


class Agent:
    def __init__(
        self,
        session: Session,
        embedder: Embedder,
        reranker: Reranker | None = None,
    ) -> None:
        self.session = session
        self.embedder = embedder
        self.reranker = reranker
        self.cfg = get_config().agent

    def ask(
        self,
        question: str,
        *,
        filters: Filters,
        history: list[tuple[str, str]] | None = None,
        k: int = 8,
        prefer_local: bool = False,  # <--- ADDED THIS
    ) -> AgentResult:
        t0 = time.perf_counter()
        attempts: list[Attempt] = []
        final_result: AskResult | None = None
        current_k = k
        gave_up = ""

        print(f"🟡 [AGENT] ask() called with prefer_local={prefer_local}")  # <--- ADD

        for iteration in range(1, self.cfg.max_iterations + 1):
            asker = Asker(self.session, self.embedder, reranker=self.reranker)
            result = asker.ask(
                question,
                filters=filters,
                history=history,
                k=current_k,
                prefer_local=prefer_local  # <--- PASS IT DOWN
            )

            suff = sufficiency_check(
                result.pipeline.doc_chunks if result.pipeline else [],
                result.pipeline.sql_evidence if result.pipeline else [],
            )

            attempts.append(Attempt(
                iteration=iteration,
                k_used=current_k,
                suff=suff,
                answer_confidence=result.answer.confidence,
                abstained=result.answer.abstained,
                note=f"suff={suff.level}",
            ))
            final_result = result

            ok_suff = suff.level == "sufficient"
            ok_conf = result.answer.confidence >= self.cfg.min_confidence
            ok_not_abstained = not result.answer.abstained

            if ok_suff and ok_conf and ok_not_abstained:
                break

            elapsed = time.perf_counter() - t0
            if elapsed >= self.cfg.latency_budget_s:
                gave_up = f"latency budget {self.cfg.latency_budget_s}s exceeded"
                break

            if iteration >= self.cfg.max_iterations:
                gave_up = (
                    f"max_iterations={self.cfg.max_iterations} reached; "
                    f"last attempt: suff={suff.level} "
                    f"confidence={result.answer.confidence:.2f} "
                    f"abstained={result.answer.abstained}"
                )
                break

            new_k = min(int(current_k * self.cfg.broaden_factor), self.cfg.max_k)
            if new_k == current_k:
                gave_up = "cannot broaden k further"
                break
            current_k = new_k

        elapsed = time.perf_counter() - t0
        assert final_result is not None

        return AgentResult(
            question=question,
            final=final_result,
            attempts=attempts,
            iterations_used=len(attempts),
            gave_up_reason=gave_up,
            elapsed_s=elapsed,
        )