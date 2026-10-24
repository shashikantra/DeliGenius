"""Pure scorers for the agent-eval harness.

Each scorer is a small, side-effect-free function: input is data
extracted from the `/ask` HTTP response (already parsed to Python
primitives), output is `bool`. No HTTP, no DB, no imports from
`deli_rag.agent.*`, no imports from `deli_rag.eval.metrics` — the
retrieval metrics live there and measure a different thing.

Why not extend `metrics.py`?
    `metrics.py` scores *chunks* (recall@k, RR, nDCG). This module
    scores *responses* (route taken, substrings present in the answer,
    abstain reason). Mixing them would force both callers to import
    code paths they don't use, and it would make a retrieval metric
    regression risk sharing a file with an agent assertion.

Why `Mapping[str, object]` instead of `dict[str, Any]`?
    `mypy --strict` is enabled in `pyproject.toml`. `Any` would
    require per-call `# type: ignore`, which is the wrong default.
    `object` forces explicit narrowing at the call site, which is
    what we want.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from deli_rag.eval.golden_agent import AbstainReason, RouteKind


def route_match(
    citations: Sequence[Mapping[str, object]],
    expected: RouteKind,
) -> bool:
    """Did the response take the expected route?

    `citations` is the list of `CitationOut` objects from `AskResponse`,
    already converted to plain dicts. Only the `kind` field is read.

    Rules (derived from DECISIONS §13.1 + §13.2):
      - `expected == "any"`  → always True (YAML did not assert a route).
      - `expected == "sql"`  → at least one citation with `kind == "sql"`.
      - `expected == "doc"`  → zero `kind=="sql"` citations AND at least
                              one `kind=="doc"` citation.

    The `doc` case explicitly requires *absence* of SQL citations, not
    just presence of a doc citation. A response that returned both a
    doc chunk and a SQL row is a route ambiguity, and we should fail
    it rather than silently pick one — that ambiguity usually means
    the router was unsure, which is exactly the failure we want to
    catch.
    """
    if expected == "any":
        return True
    kinds = [c.get("kind") for c in citations]
    has_sql = "sql" in kinds
    has_doc = "doc" in kinds
    if expected == "sql":
        return has_sql
    if expected == "doc":
        return has_doc and not has_sql
    return False  # unreachable given the Literal type; keeps mypy honest


def substring_match(answer: str, expected: Sequence[str]) -> bool:
    """Does the final answer contain *all* expected substrings (case-insensitive)?

    Semantics chosen deliberately:
      - Empty `expected` → True (nothing to assert; consistent with
        `route_match(..., "any")` = True).
      - Empty `answer`   → False unless `expected` is empty. An abstain
        answer ("Item not found") is non-empty; a genuinely empty
        answer is a bug in the pipeline and should fail.
      - Case-insensitive because the answer LLM varies casing (e.g.
        "marlboro" vs "Marlboro"), and we are asserting *information
        presence*, not exact wording.
    """
    if not expected:
        return True
    if not answer:
        return False
    hay = answer.lower()
    return all(s.lower() in hay for s in expected)


def abstain_match(
    *,
    abstained: bool,
    needs_clarification: str | None,
    answer: str,
    citations: Sequence[Mapping[str, object]],
    expect: AbstainReason | None,
) -> bool:
    """Did the response abstain for the *expected reason*?

    Two abstain modes exist in this codebase and they are not the same:

      - `not_found` — the pipeline ran, `text_to_sql.py` produced a
        valid query, the DB returned zero rows, and `ask.py` phrased
        a clean "Item not found". Distinguishing feature: the
        response has *no* SQL citation (there was nothing to cite),
        and `needs_clarification` is typically None.

      - `acl` — the filters removed every candidate before retrieval
        even ran (golden item `acl-blocked`). Distinguishing feature:
        *zero* citations of any kind, and the answer is short and
        does not mention a specific item.

    `expect is None` with `abstained is True` means "abstained, and we
    do not care why" — useful during triage before a reason is
    established. `expect is not None` with `abstained is False` is a
    hard failure (the pipeline answered a question it should have
    declined).
    """
    if expect is None:
        # Caller is not asserting a reason. Pass iff abstain state matches
        # what the YAML's `should_abstain` field implies (checked by the
        # CLI, not here) — this function is neutral on abstain==True/False
        # when no reason was requested.
        return True
    if not abstained:
        return False

    kinds = [c.get("kind") for c in citations]
    has_any_citation = len(kinds) > 0

    if expect == "not_found":
        # No SQL citation (nothing to cite) and no doc citation (we did
        # not fall back to vector search on a miss — per DECISIONS §13.1
        # the fallback is a clean abstain, not a doc lookup).
        return not has_any_citation and needs_clarification is None

    if expect == "acl":
        # ACL abstain: nothing to cite, and the answer should not be a
        # clarification request (there is no user-input to clarify —
        # the data simply is not visible).
        return not has_any_citation and needs_clarification is None

    return False  # unreachable given the Literal type


# Convenience alias used by the CLI's result aggregation. Kept here so
# the CLI doesn't grow an "if/else ladder" per item.
ScorerResult = Literal["pass", "fail"]