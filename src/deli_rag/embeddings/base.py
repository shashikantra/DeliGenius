from __future__ import annotations

from typing import Protocol

from deli_rag.config.settings import get_config


class Embedder(Protocol):
    """Every embedder implements this. Dimensionality must match the DB schema."""
    name: str
    dim: int
    model_version: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents for indexing. No query prefix."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query. May apply a model-specific query prefix."""
        ...


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Singleton factory. Model name + dim come from config/base.yaml."""
    global _embedder
    if _embedder is not None:
        return _embedder
    cfg = get_config().embedder
    if cfg.name == "BAAI/bge-small-en-v1.5":
        from .bge_small import BgeSmallEmbedder
        _embedder = BgeSmallEmbedder(
            model_name=cfg.name, dim=cfg.dim, normalize=cfg.normalize,
        )
    else:
        raise ValueError(f"Unknown embedder in config: {cfg.name!r}")
    return _embedder