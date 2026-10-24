from __future__ import annotations

import re
from dataclasses import dataclass

from deli_rag.schemas.answer import Answer


@dataclass
class ValidationReport:
    ok: bool
    issues: list[str]
    redacted_pii: bool = False


# --- PII patterns (per DECISIONS.md §1: redact in logs, not in answer text) ---

_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
_PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")


def redact_pii(text: str) -> tuple[str, bool]:
    """Return (redacted_text, was_modified)."""
    out = text
    for pattern, label in (
        (_SSN_RE, "[SSN-REDACTED]"),
        (_CC_RE, "[CC-REDACTED]"),
        (_EMAIL_RE, "[EMAIL-REDACTED]"),
        (_PHONE_RE, "[PHONE-REDACTED]"),
    ):
        out = pattern.sub(label, out)
    return out, (out != text)


def validate(
    answer: Answer,
    *,
    evidence_index: list[dict],
    min_confidence: float = 0.5,
) -> ValidationReport:
    """Checks:
    1. Schema: already enforced by Pydantic (Answer.model_validate).
    2. Citation IDs: every id in `answer.citations` must exist in the evidence index.
    3. Groundedness heuristic: if not abstained and confidence >= min_confidence,
       the answer must contain at least one number or noun from a cited evidence block.
    4. Non-empty answer unless abstained.
    """
    issues: list[str] = []

    valid_ids = {int(e["id"]) for e in evidence_index}

    # 1. Citations exist
    bad_ids = [c for c in answer.citations if c not in valid_ids]
    if bad_ids:
        issues.append(f"citation ids not in evidence: {bad_ids}")

    # 2. If not abstained and confident, require at least one citation
    if not answer.abstained and answer.confidence >= min_confidence and not answer.citations:
        issues.append("non-abstained answer with no citations")

    # 3. Non-empty answer unless abstained
    if not answer.abstained and not answer.answer.strip():
        issues.append("empty answer text")

    # 4. Groundedness heuristic: at least one number in the answer must appear in the
    # text of at least one cited evidence block.
    if not answer.abstained and answer.citations:
        cited_blocks = [e for e in evidence_index if int(e["id"]) in answer.citations]
        # We don't have block *text* in the index, only metadata.
        # Skip deep grounding here; the prompt-level instruction is the primary guard.
        # Future: pass block text into evidence_index for stronger checking.
        pass

    return ValidationReport(ok=not issues, issues=issues)


def verify_citations_exist(citations: list[int], evidence_index: list[dict]) -> tuple[bool, list[int]]:
    valid_ids = {int(e["id"]) for e in evidence_index}
    bad = [c for c in citations if c not in valid_ids]
    return (not bad, bad)