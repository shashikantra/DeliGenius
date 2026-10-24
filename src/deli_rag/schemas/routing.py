from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Route = Literal["doc_retrieval", "sql", "both", "abstain"]


class RoutingDecision(BaseModel):
    """What to do with one sub-question."""
    sub_question: str
    route: Route
    sql_kind: str | None = None      # which SQL handler, if sql or both
    reason: str = ""
    confidence: float = 0.0


class RoutedQuery(BaseModel):
    original: str
    sub_questions: list[str] = Field(default_factory=list)
    decisions: list[RoutingDecision] = Field(default_factory=list)

    def unique_routes(self) -> set[str]:
        return {d.route for d in self.decisions}