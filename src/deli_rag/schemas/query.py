from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["fact", "comparison", "policy", "troubleshooting", "summary", "other"]


class Entities(BaseModel):
    """Entities extracted from a query. All optional; missing = not present."""
    dates: list[str] = Field(default_factory=list)         # raw date strings as written
    amounts: list[str] = Field(default_factory=list)       # "$1,560.80", "216.56"
    skus: list[str] = Field(default_factory=list)          # UPCs or SKU codes
    branches: list[str] = Field(default_factory=list)      # NJ2479
    categories: list[str] = Field(default_factory=list)    # Drinks, Snacks, Cigarettes
    vendors: list[str] = Field(default_factory=list)       # RIA, Marlboro, Gatorade

    def is_empty(self) -> bool:
        return not any([self.dates, self.amounts, self.skus,
                        self.branches, self.categories, self.vendors])


class UnderstoodQuery(BaseModel):
    original: str
    normalized: str                    # lowercased, punctuation-stripped
    intent: Intent
    entities: Entities
    is_ambiguous: bool = False
    clarification_question: str | None = None
    reason: str = ""                   # why this intent was chosen


class TransformedQuery(BaseModel):
    original: str
    rewritten: str                     # standalone, no unresolved pronouns
    expanded: str                      # synonyms applied
    sub_questions: list[str] = Field(default_factory=list)   # for multi-part queries
    transformations_applied: list[str] = Field(default_factory=list)

    def all_queries(self) -> list[str]:
        """Every distinct query string to run through retrieval."""
        out: list[str] = [self.expanded]
        for sq in self.sub_questions:
            if sq not in out:
                out.append(sq)
        return out