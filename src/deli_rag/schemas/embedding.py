from datetime import datetime

from pydantic import BaseModel


class Embedding(BaseModel):
    chunk_id: str
    model_name: str
    model_version: str                # e.g. "v1" — lets us reindex when embedder changes
    vector: list[float]
    created_at: datetime