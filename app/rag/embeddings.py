from functools import lru_cache

import numpy as np
from fastembed import TextEmbedding

MODEL_NAME = "BAAI/bge-small-en-v1.5"


class EmbeddingService:
    def __init__(self, model_name: str = MODEL_NAME):
        self.model = TextEmbedding(
            model_name=model_name,
            lazy_load=True,
        )

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self.model.embed(
            texts,
            batch_size=32,
        )

        return [embedding.tolist() for embedding in embeddings]

    def embed_query(self, text: str) -> list[float]:
        embedding = next(
            self.model.embed([text]),
        )

        return embedding.tolist()

    @property
    def dimension(self) -> int:
        return len(
            next(
                self.model.embed(["dimension check"]),
            )
        )


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()