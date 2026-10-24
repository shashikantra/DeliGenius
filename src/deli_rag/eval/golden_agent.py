"""Agent-behaviour golden-set loader.

Why this file exists
--------------------
`deli_rag/eval/golden.py` defines the *retrieval*-shaped golden schema
(`GoldenItem`): it asserts that the right chunk is returned from
`HybridRetriever` for a given question. It has no concept of routing,
SQL generation, or end-to-end answers.

DECISIONS.md §14 ("Golden Questions") requires an *agent*-shaped
assertion: did the pipeline route to SQL? did it return the right
numeric value? did it abstain cleanly when the item is unknown, and
*separately* when ACL filtering hides the data?

Those assertions need three extra fields that `GoldenItem` does not
have (`expected_route`, `expect_abstain_reason`) plus a different
meaning for `should_abstain` (an *assertion*, not a skip flag).

This module parses the **same** YAML file as `golden.py` but produces
a different dataclass. The two loaders are deliberately not coupled:
Pydantic's default `extra="ignore"` means adding new keys to the YAML
is a no-op for `GoldenItem` (so the retrieval harness keeps passing
unchanged), and future schema changes in one loader cannot perturb
the other.

Do not import `GoldenSet` here. Do not make `GoldenSet` import this.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

# Enum-like literals. Kept as `Literal` (not `enum.Enum`) so the YAML
# stays human-editable as plain strings and mypy sees the closed set.
RouteKind = Literal["sql", "doc", "any"]
AbstainReason = Literal["not_found", "acl"]


class GoldenAgentItem(BaseModel):
    """One agent-behaviour assertion from the golden set.

    Fields that overlap with `GoldenItem` are intentionally re-declared
    here so this class has *no* dependency on `GoldenItem`. If the two
    schemas diverge in the future, this class stays self-contained.
    """

    id: str
    question: str
    expected_substrings: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    acl_levels: list[str] = Field(default_factory=lambda: ["public", "internal"])
    tenant: str = "default"
    should_abstain: bool = False

    # --- Agent-only fields (optional; retrieval golden sets omit them) ---
    # "any" means: the YAML did not assert a route; do not fail on routing.
    expected_route: RouteKind = "any"
    # Distinguishes two abstain modes that DECISIONS §14 distinguishes:
    #   "not_found" — pipeline ran, SQL returned 0 rows, LLM said "Item not found"
    #   "acl"       — ACL filters removed all candidates; nothing to answer from
    # `None` with `should_abstain=True` means "abstained, reason not asserted".
    expect_abstain_reason: AbstainReason | None = None


class GoldenAgentSet(BaseModel):
    version: str
    description: str = ""
    items: list[GoldenAgentItem]


def load_golden_agent_set(path: Path) -> GoldenAgentSet:
    """Load and validate an agent-shape golden set from YAML.

    Raises `pydantic.ValidationError` on schema mismatch; raises
    `FileNotFoundError` if `path` is missing. Deliberately does not
    swallow either — a bad golden set must fail loudly, not silently
    produce an empty run.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GoldenAgentSet(**raw)