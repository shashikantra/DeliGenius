from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from deli_rag.schemas import Document


Decision = Literal["insert_new", "new_version", "skip_identical"]


@dataclass
class DedupDecision:
    decision: Decision
    doc_version: int
    supersedes_doc_id: str | None      # doc_id of the version being replaced, if any
    reason: str


def decide(
    *,
    candidate: Document,
    existing_versions: list[Document],
) -> DedupDecision:
    """Given a newly-parsed document and any prior versions of the same logical doc_id,
    decide what to do.

    Rules (per DECISIONS.md §4):
    - No existing versions → insert_new, version 1.
    - Latest existing has the same content_hash → skip_identical.
    - Latest existing has a different content_hash → new_version (increment),
      and the previous version becomes superseded_by the new one.
    """
    if not existing_versions:
        return DedupDecision(
            decision="insert_new",
            doc_version=1,
            supersedes_doc_id=None,
            reason="no prior versions of this logical doc_id",
        )

    latest = max(existing_versions, key=lambda d: d.doc_version)
    if latest.content_hash == candidate.content_hash:
        return DedupDecision(
            decision="skip_identical",
            doc_version=latest.doc_version,
            supersedes_doc_id=None,
            reason=f"content_hash matches existing version {latest.doc_version}",
        )
    return DedupDecision(
        decision="new_version",
        doc_version=latest.doc_version + 1,
        supersedes_doc_id=latest.doc_id,
        reason=f"content_hash differs from version {latest.doc_version}",
    )