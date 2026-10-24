from __future__ import annotations

from deli_rag.agent.router import route
from deli_rag.agent.transform import transform
from deli_rag.agent.understanding import understand


def _routed(q: str):
    u = understand(q)
    t = transform(q)
    return route(u, t)


def test_reorder_query_routes_to_sql():
    r = _routed("which items are below the reorder threshold?")
    # Reorder signal + fact/both intent → sql (strong signal + entity)
    assert r.decisions[0].route in ("sql", "both")
    assert r.decisions[0].sql_kind == "reorder_candidates"


def test_ria_commission_routes_to_ria_summary():
    r = _routed("what is our RIA commission for May 2026?")
    assert r.decisions[0].sql_kind == "ria_summary"
    assert r.decisions[0].route in ("sql", "both")


def test_policy_query_uses_doc_retrieval():
    r = _routed("what is the refund policy?")
    # No SQL handler for a policy question → default doc_retrieval
    assert r.decisions[0].route == "doc_retrieval"
    assert r.decisions[0].sql_kind is None


def test_ambiguous_short_query_abstains():
    r = _routed("what about it?")
    assert r.decisions[0].route == "abstain"


def test_decomposition_produces_one_decision_per_subq():
    r = _routed("What was our sales last week, and what about inventory?")
    assert len(r.decisions) >= 2
    # Every sub-question gets its own decision
    assert all(d.sub_question for d in r.decisions)


def test_unique_routes_helper():
    r = _routed("What was our sales last week, and what about inventory?")
    assert r.unique_routes()