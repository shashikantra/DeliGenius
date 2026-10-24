from __future__ import annotations

from typing import Protocol

from deli_rag.config.settings import get_config


class Reranker(Protocol):
    """Cross-encoder reranker. One score per candidate. Higher = more relevant."""
    name: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...


_reranker: Reranker | None = None


def get_reranker() -> Reranker:
    global _reranker
    if _reranker is not None:
        return _reranker
    cfg = get_config().reranker
    if cfg.name == "BAAI/bge-reranker-base":
        from .bge_reranker import BgeReranker
        _reranker = BgeReranker(model_name=cfg.name)
    else:
        raise ValueError(f"Unknown reranker in config: {cfg.name!r}")
    return _reranker