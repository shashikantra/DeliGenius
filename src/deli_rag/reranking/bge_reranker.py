from __future__ import annotations

from functools import cached_property


class BgeReranker:
    """Cross-encoder reranker via sentence-transformers CrossEncoder."""

    def __init__(self, *, model_name: str = "BAAI/bge-reranker-base", batch_size: int = 16) -> None:
        self.name = model_name
        self.batch_size = batch_size

    @cached_property
    def _model(self):
        from sentence_transformers import CrossEncoder
        return CrossEncoder(self.name, max_length=512)

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, p) for p in passages]
        scores = self._model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        return [float(s) for s in scores]