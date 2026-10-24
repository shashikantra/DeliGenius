"""Unit tests for `deli_rag.eval.scorers_agent`.

Pure-function tests. No fixtures, no HTTP, no DB, no `/ask` call.
Rationale: if a scorer is wrong, every live eval run is meaningless;
the scorers must be provably correct *before* the harness makes any
network call. `pytest` collects this file under the existing
`testpaths = ["tests"]` setting in `pyproject.toml`.
"""

from __future__ import annotations

import pytest

from deli_rag.eval.scorers_agent import (
    abstain_match,
    route_match,
    substring_match,
)


# ----------------------------- route_match -----------------------------


def _c(*kinds: str) -> list[dict[str, object]]:
    return [{"id": i, "kind": k} for i, k in enumerate(kinds, start=1)]


@pytest.mark.parametrize(
    "kinds, expected, want",
    [
        ((), "any", True),
        (("sql",), "any", True),
        (("doc",), "any", True),
        (("sql",), "sql", True),
        (("doc",), "sql", False),
        ((), "sql", False),
        (("sql", "doc"), "sql", True),       # SQL present anywhere → pass
        (("doc",), "doc", True),
        (("sql",), "doc", False),
        ((), "doc", False),
        (("sql", "doc"), "doc", False),      # ambiguous route → fail
        (("doc", "doc"), "doc", True),
    ],
)
def test_route_match(kinds: tuple[str, ...], expected: str, want: bool) -> None:
    assert route_match(_c(*kinds), expected) is want  # type: ignore[arg-type]


def test_route_match_ignores_non_kind_fields() -> None:
    # A citation may carry sql_summary, sql_query, etc. Those must not
    # affect route detection.
    cits = [
        {"id": 1, "kind": "sql", "sql_query": "SELECT 1", "sql_data": [[1]]},
        {"id": 2, "kind": "doc", "filename": "policy.pdf"},
    ]
    assert route_match(cits, "sql") is True
    assert route_match(cits, "doc") is False


# --------------------------- substring_match ---------------------------


@pytest.mark.parametrize(
    "answer, expected, want",
    [
        ("", [], True),                              # nothing to assert
        ("", ["x"], False),
        ("Marlboro Red Filter costs 16.50", ["Marlboro"], True),
        ("marlboro red filter costs 16.50", ["Marlboro"], True),   # case-insensitive
        ("Marlboro Red Filter costs 16.50", ["16.50"], True),
        ("Marlboro Red Filter costs 16.50", ["16.51"], False),
        ("Marlboro Red Filter costs 16.50", ["Marlboro", "16.50"], True),
        ("Marlboro Red Filter costs 16.50", ["Marlboro", "17.00"], False),
    ],
)
def test_substring_match(answer: str, expected: list[str], want: bool) -> None:
    assert substring_match(answer, expected) is want


# ---------------------------- abstain_match ----------------------------


def test_abstain_none_expectation_never_fails() -> None:
    # expect=None means "we are not asserting the reason"; the CLI is
    # responsible for asserting `should_abstain` state separately.
    for abstained in (True, False):
        assert abstain_match(
            abstained=abstained, needs_clarification=None, answer="",
            citations=[], expect=None,
        ) is True


def test_abstain_not_found_happy_path() -> None:
    # Zero citations, no clarification, abstained=True, expect=not_found.
    assert abstain_match(
        abstained=True,
        needs_clarification=None,
        answer="Item not found.",
        citations=[],
        expect="not_found",
    ) is True


def test_abstain_not_found_but_had_citations_fails() -> None:
    # If citations came back, the "not found" narrative is inconsistent.
    assert abstain_match(
        abstained=True,
        needs_clarification=None,
        answer="Item not found.",
        citations=[{"id": 1, "kind": "sql"}],
        expect="not_found",
    ) is False


def test_abstain_not_found_but_did_not_abstain_fails() -> None:
    assert abstain_match(
        abstained=False,
        needs_clarification=None,
        answer="The price is 1.99.",
        citations=[],
        expect="not_found",
    ) is False


def test_abstain_acl_happy_path() -> None:
    assert abstain_match(
        abstained=True,
        needs_clarification=None,
        answer="I don't have access to that information.",
        citations=[],
        expect="acl",
    ) is True


def test_abstain_acl_with_clarification_fails() -> None:
    # ACL abstain should not ask the user for clarification — the data
    # is not visible, no user input can unblock it in a single turn.
    assert abstain_match(
        abstained=True,
        needs_clarification="Which employee?",
        answer="",
        citations=[],
        expect="acl",
    ) is False


def test_abstain_acl_with_citations_fails() -> None:
    assert abstain_match(
        abstained=True,
        needs_clarification=None,
        answer="Here is what I found.",
        citations=[{"id": 1, "kind": "doc"}],
        expect="acl",
    ) is False