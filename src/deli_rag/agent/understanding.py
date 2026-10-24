from __future__ import annotations

import re

from deli_rag.schemas.query import Entities, Intent, UnderstoodQuery


# --- intent patterns (ordered: first match wins) ---

_INTENT_PATTERNS: list[tuple[Intent, list[re.Pattern]]] = [
    ("summary", [
        re.compile(r"\b(summar(y|ize|ise)|overview|recap)\b", re.I),
        re.compile(r"\bwhat('s| is) (the )?(total|overall)\b", re.I),
    ]),
    ("comparison", [
        re.compile(r"\b(compare|vs\.?|versus|difference between|higher|lower|more than|less than)\b", re.I),
        re.compile(r"\b(better|worse|best|worst)\b", re.I),
    ]),
    ("troubleshooting", [
        re.compile(r"\b(why (is|does|did)|how (do|can) i fix|not working|error|issue|problem|broken)\b", re.I),
    ]),
    ("policy", [
        re.compile(r"\b(policy|rule|procedure|allowed|permitted|required)\b", re.I),
        re.compile(r"\b(how (do|should) (we|i) (handle|process|do))\b", re.I),
    ]),
    ("fact", [
        # Default once a question mark or a wh-word is present
        re.compile(r"^(what|who|when|where|which|how much|how many|how often|how long)\b", re.I),
    ]),
]


# --- entity patterns ---

_DATE_PATTERNS = [
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,?\s*\d{4})?\b", re.I),
    re.compile(r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?(?:\s+\d{4})?\b", re.I),
    re.compile(r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{4})?\b", re.I),
]

_AMOUNT_RE = re.compile(r"\$\s?\d[\d,]*\.?\d*|\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b")
_AMOUNT_STRICT = re.compile(r"\$\s?\d[\d,]*\.?\d*|\b\d[\d,]*\.\d{2}\b")

_SKU_RE = re.compile(r"\b(?:SKU[-_]?\d{3,}|0\d{10,14}|\d{12,14})\b")
_BRANCH_RE = re.compile(r"\b[A-Z]{2}\d{4,6}\b")
_CATEGORY_WORDS = {"drinks", "snacks", "candy", "cigarettes", "household",
                   "grocery", "produce", "dairy", "frozen", "vapes", "water",
                   "cleaning", "laundry", "general food", "tobacco",
                   "ice cream", "sandwich", "medicine", "hygiene"}
_VENDOR_WORDS = {"ria", "rimi", "rimi deli", "marlboro", "newport", "gatorade",
                 "monster", "snapple", "goya", "maruchan", "colgate", "oreo",
                 "snickers", "twix", "haagen", "tropicana", "nestle",
                 "pepperidge", "jack link", "doritos", "cheetos"}


def understand(query: str) -> UnderstoodQuery:
    normalized = _normalize(query)
    intent, reason = _classify_intent(normalized)
    entities = _extract_entities(query, normalized)
    ambiguous, clarification = _check_ambiguity(query, intent, entities)
    return UnderstoodQuery(
        original=query,
        normalized=normalized,
        intent=intent,
        entities=entities,
        is_ambiguous=ambiguous,
        clarification_question=clarification,
        reason=reason,
    )


# --- internals ---

def _normalize(text: str) -> str:
    text = text.strip().lower()
    # collapse whitespace, keep letters/digits/space/punct we care about
    text = re.sub(r"\s+", " ", text)
    return text


def _classify_intent(normalized: str) -> tuple[Intent, str]:
    for intent, patterns in _INTENT_PATTERNS:
        for p in patterns:
            if p.search(normalized):
                return intent, f"matched pattern {p.pattern!r}"
    if normalized.endswith("?"):
        return "fact", "ends with '?' but no specific pattern matched"
    return "other", "no pattern matched"


def _extract_entities(original: str, normalized: str) -> Entities:
    e = Entities()
    for p in _DATE_PATTERNS:
        for m in p.finditer(original):
            v = m.group(0).strip()
            if v and v not in e.dates:
                e.dates.append(v)
    for m in _AMOUNT_STRICT.finditer(original):
        v = m.group(0).strip()
        if v and v not in e.amounts:
            e.amounts.append(v)
    for m in _SKU_RE.finditer(original):
        v = m.group(0).strip()
        if v and v not in e.skus:
            e.skus.append(v)
    for m in _BRANCH_RE.finditer(original):
        v = m.group(0).strip()
        if v and v not in e.branches:
            e.branches.append(v)
    for cat in _CATEGORY_WORDS:
        if re.search(rf"\b{re.escape(cat)}\b", normalized):
            if cat not in e.categories:
                e.categories.append(cat)
    for v in _VENDOR_WORDS:
        if re.search(rf"\b{re.escape(v)}\b", normalized):
            if v not in e.vendors:
                e.vendors.append(v)
    return e


def _check_ambiguity(original: str, intent: Intent, entities: Entities) -> tuple[bool, str | None]:
    """Trigger a clarifying question only when we're confident we'd guess wrong.
    Conservative by design — false positives hurt more than false negatives here."""
    norm = original.lower().strip()
    words = norm.split()

    # Pronoun-only follow-up with no actionable content. Match either a very short
    # query (<= 4 words) or a query that is nothing but anaphora + a wh-word.
    has_pronoun = bool(re.search(r"\b(it|that|this|those|them|these)\b", norm))
    has_substantive_noun = bool(re.search(
        r"\b(commission|sales|inventory|stock|refund|hours|policy|report|"
        r"balance|deposit|transfer|sku|upc|category|amount|total)\b",
        norm,
    ))
    if has_pronoun and not has_substantive_noun and len(words) <= 5:
        return True, ("Could you rephrase that as a full question? "
                      "I don't have context to know what 'it' refers to.")

    # "How much X" with no entity and no obvious target noun
    if re.match(r"^how (much|many)\b", norm) and entities.is_empty():
        if not re.search(r"\b(sold|commission|spent|left|in stock|on hand)\b", norm):
            return True, ("How much of what, specifically? A product name, category, "
                          "or SKU would help me narrow it down.")

    return False, None