from __future__ import annotations

from deli_rag.agent.understanding import understand


def test_intent_fact():
    u = understand("what was our RIA commission for May?")
    assert u.intent == "fact"
    assert "commission" in u.normalized


def test_intent_comparison():
    u = understand("Compare Q2 vs Q3 revenue")
    assert u.intent == "comparison"


def test_intent_policy():
    u = understand("What is the refund policy?")
    assert u.intent == "policy"


def test_intent_summary():
    u = understand("Summarize our RIA activity last week")
    assert u.intent == "summary"


def test_intent_troubleshooting():
    u = understand("Why is the register not working?")
    assert u.intent == "troubleshooting"


def test_entity_dates():
    u = understand("How much did we sell on 2026-06-22?")
    assert "2026-06-22" in u.entities.dates


def test_entity_dates_month_name():
    u = understand("how much commission was paid for May 2026?")
    assert any("may 2026" in d.lower() for d in u.entities.dates)


def test_entity_amounts():
    u = understand("did we collect $1,560.80 in deposits?")
    assert any("1,560.80" in a for a in u.entities.amounts)


def test_entity_branch():
    u = understand("show me NJ2479 activity")
    assert "NJ2479" in u.entities.branches


def test_entity_vendors_and_categories():
    u = understand("how many Marlboro cigarettes do we have in Candy?")
    assert "marlboro" in u.entities.vendors
    # Category matching requires the exact word; "candy" is in the list
    assert "candy" in u.entities.categories


def test_ambiguity_pronoun_only():
    u = understand("what about it?")
    assert u.is_ambiguous is True
    assert u.clarification_question


def test_ambiguity_how_much_no_entity():
    u = understand("how much?")
    assert u.is_ambiguous is True


def test_no_false_positive_ambiguity():
    u = understand("what was our RIA commission for May 2026?")
    assert u.is_ambiguous is False