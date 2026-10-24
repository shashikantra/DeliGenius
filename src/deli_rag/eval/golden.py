from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class GoldenItem(BaseModel):
    id: str
    question: str
    expected_substrings: list[str] = Field(default_factory=list)
    reference_answer: str | None = None
    acl_levels: list[str] = Field(default_factory=lambda: ["public", "internal"])
    tenant: str = "default"
    should_abstain: bool = False


class GoldenSet(BaseModel):
    version: str
    description: str = ""
    items: list[GoldenItem]


def load_golden_set(path: Path) -> GoldenSet:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return GoldenSet(**raw)