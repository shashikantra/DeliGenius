from __future__ import annotations

import re

from deli_rag.schemas.query import TransformedQuery


# Domain-specific synonym map. Left side = what users type; right = what's in the corpus.
_SYNONYMS: dict[str, str] = {
    "ria": "Rimi Deli RIA",
    "rimi": "Rimi Deli",
    "money transfer": "MT Send RIA",
    "mt send": "MT Send",
    "commission": "commission Commission",
    "inventory": "Inventory In Stock",
    "stock": "In Stock",
    "reorder": "Reorder Now Count Threshold",
    "out of stock": "In Stock 0",
    "sales": "Sales Total Amount",
    "revenue": "Total Amount",
    "items": "UPC",
    "products": "UPC",
    "cigarettes": "Cigarettes Tobacco",
    "soda": "Drinks",
    "beverages": "Drinks Water",
    "chips": "Snacks",
    "candy": "Candy",
    "policy": "Policy",
    "refund": "Refund",
    "store hours": "Store Hours Monday",
    "hours": "Store Hours Monday",
}


# --- follow-up detection ---

_PRONOUN_RE = re.compile(r"\b(it|that|this|those|them|these|he|she|they)\b", re.I)
_ANAPHORIC_STARTS = re.compile(
    r"^(and |also |what about|how about|now |then |what else|who else|"
    r"same |the same |more |those |that )",
    re.I,
)


def transform(
    query: str,
    *,
    history: list[tuple[str, str]] | None = None,
) -> TransformedQuery:
    """Turn a raw user query into retrieval-ready text.

    - Rewrites follow-ups using the last (user, assistant) turn for context.
    - Expands synonyms that reflect corpus vocabulary.
    - Decomposes multi-part questions ("X and Y?", "X, and what about Y?")
    """
    applied: list[str] = []
    history = history or []

    # 1. Rewrite follow-up → standalone
    rewritten = query
    if history and _is_followup(query):
        rewritten = _rewrite_with_history(query, history)
        if rewritten != query:
            applied.append("history_rewrite")

    # 2. Expand synonyms
    expanded = _expand_synonyms(rewritten)
    if expanded != rewritten:
        applied.append("synonym_expansion")

    # 3. Decompose
    sub_questions = _decompose(rewritten)
    if sub_questions:
        applied.append("decomposition")

    return TransformedQuery(
        original=query,
        rewritten=rewritten,
        expanded=expanded,
        sub_questions=sub_questions,
        transformations_applied=applied,
    )


# --- internals ---

def _is_followup(query: str) -> bool:
    q = query.strip()
    if not q:
        return False
    if _ANAPHORIC_STARTS.match(q):
        return True
    if _PRONOUN_RE.search(q) and len(q.split()) <= 8:
        return True
    # "What about X?" style
    if q.lower().startswith("what about"):
        return True
    return False


def _rewrite_with_history(query: str, history: list[tuple[str, str]]) -> str:
    """Prepend the last user question's topic if the current query starts anaphorically
    or relies on an unresolved pronoun."""
    last_user = history[-1][0] if history else ""
    if not last_user:
        return query

    # Extract the noun-phrase-ish tail of the previous question (heuristic)
    topic = _extract_topic(last_user)
    if not topic:
        return query

    # Strip anaphoric opener
    stripped = re.sub(
        r"^(and |also |what about|how about|now |then )",
        "", query.strip(), flags=re.I,
    ).strip()

    if not stripped:
        return query

    # If the query is a pronoun sentence, replace pronoun with topic
    if _PRONOUN_RE.search(stripped) and len(stripped.split()) <= 6:
        return _PRONOUN_RE.sub(topic, stripped, count=1)

    return f"{topic} — {stripped}"


def _extract_topic(question: str) -> str:
    """Best-effort: take the longest noun-ish chunk of the previous question.
    Heuristic; good enough for the corpus we're handling."""
    q = question.strip().rstrip("?").lower()
    # Remove wh-words and short function words
    q = re.sub(r"^(what|how much|how many|when|where|who|which)\b", "", q).strip()
    q = re.sub(r"^(was|is|were|are|did|do|does|our|the|a|an)\b", "", q).strip()
    # Cut at common clause boundaries
    q = re.split(r"\b(?:for|on|in|at|from|of)\b", q)[0].strip()
    return q


def _expand_synonyms(text: str) -> str:
    """Append corpus-vocabulary synonyms in-place (does not replace user text,
    just augments it for the retriever)."""
    appended: list[str] = []
    lower = text.lower()
    for user_term, corpus_term in _SYNONYMS.items():
        if user_term in lower and corpus_term.lower() not in lower:
            appended.append(corpus_term)
    if not appended:
        return text
    return text + " " + " ".join(appended)


def _decompose(query: str) -> list[str]:
    """Split multi-part questions into standalone sub-questions.
    Conservative: only splits on clear conjunctions followed by a wh-word or command."""
    q = query.strip().rstrip("?")
    parts: list[str] = []

    # Split on "and what/what/how/where/when/who/why/which"
    m = re.split(r"\b(?:and|,)\s+(?=(?:what|how|when|where|who|why|which)\b)",
                 q, flags=re.I)
    if len(m) >= 2:
        for p in m:
            p = p.strip()
            if p:
                parts.append(p)

    # Split on " vs " and " versus "
    if not parts:
        m = re.split(r"\s+(?:vs\.?|versus)\s+", q, flags=re.I)
        if len(m) == 2:
            parts = [p.strip() for p in m if p.strip()]

    return parts if len(parts) >= 2 else []