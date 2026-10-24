from __future__ import annotations

from functools import cached_property

from .base import Embedder


# bge-small-en-v1.5 was trained with this prefix on the *query* side only.
# Prepending it to documents hurts recall; not prepending it to queries also hurts.
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class BgeSmallEmbedder:
    """BAAI/bge-small-en-v1.5 via sentence-transformers, CPU-friendly."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-small-en-v1.5",
        dim: int = 384,
        normalize: bool = True,
        model_version: str = "v1",
        batch_size: int = 32,
    ) -> None:
        self.name = model_name
        self.dim = dim
        self.normalize = normalize
        self.model_version = model_version
        self.batch_size = batch_size

    @cached_property
    def _model(self):
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(self.name)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [v.tolist() for v in vectors]

    def embed_query(self, text: str) -> list[float]:
        vec = self._model.encode(
            [_QUERY_PREFIX + text],
            batch_size=1,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
            convert_to_numpy=True,
        )[0]
        return vec.tolist()