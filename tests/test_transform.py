from __future__ import annotations

from deli_rag.agent.transform import transform


def test_synonym_expansion():
    t = transform("what is our RIA commission?")
    assert "synonym_expansion" in t.transformations_applied
    assert "Rimi Deli" in t.expanded
    assert "Commission" in t.expanded


def test_no_synonym_duplication():
    # Corpus term already present → no duplicate
    t = transform("show me Rimi Deli commission")
    # "Rimi Deli" already in text, so the synonym expansion for "ria" shouldn't
    # re-add it. It may still expand "commission" or others.
    assert t.expanded.count("Rimi Deli") == 1


def test_followup_rewrite_with_history():
    history = [("what was our RIA commission for May 2026?", "216.56 was paid for May.")]
    t = transform("what about June?", history=history)
    assert "history_rewrite" in t.transformations_applied
    assert "may 2026" in t.rewritten.lower() or "ria commission" in t.rewritten.lower()


def test_no_followup_without_history():
    t = transform("what about June?")
    # No history → no rewrite even though the query looks anaphoric
    assert "history_rewrite" not in t.transformations_applied


def test_decomposition_and_what():
    t = transform("What was our sales last week, and what about inventory?")
    assert "decomposition" in t.transformations_applied
    assert len(t.sub_questions) >= 2


def test_decomposition_vs():
    t = transform("Newport vs Marlboro sales")
    assert "decomposition" in t.transformations_applied
    assert len(t.sub_questions) == 2


def test_no_decomposition_single_question():
    t = transform("What was our RIA commission for May?")
    assert "decomposition" not in t.transformations_applied
    assert t.sub_questions == []


def test_all_queries_deduped():
    t = transform("RIA commission")
    # expanded is the only query if there are no sub-questions
    assert t.all_queries() == [t.expanded]