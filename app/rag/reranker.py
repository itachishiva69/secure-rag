from dataclasses import dataclass
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.schemas.query import RetrievedChunk


RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


@dataclass(frozen=True)
class RerankedChunk:
    chunk: RetrievedChunk
    score: float


class Reranker:
    def __init__(
        self,
        model_name: str = RERANKER_MODEL,
    ):
        self.model = CrossEncoder(
            model_name,
            device="cpu",
        )

    def rerank(
        self,
        *,
        query: str,
        chunks: list[RetrievedChunk],
        limit: int = 5,
    ) -> list[RerankedChunk]:
        if not query.strip():
            raise ValueError(
                "Query cannot be empty"
            )

        if limit <= 0:
            raise ValueError(
                "limit must be greater than zero"
            )

        if not chunks:
            return []

        pairs = [
            (
                query,
                chunk.text,
            )
            for chunk in chunks
        ]

        scores = self.model.predict(
            pairs,
            show_progress_bar=False,
        )

        ranked = [
            RerankedChunk(
                chunk=chunk,
                score=float(score),
            )
            for chunk, score in zip(
                chunks,
                scores,
            )
        ]

        ranked.sort(
            key=lambda result: result.score,
            reverse=True,
        )

        return ranked[:limit]


@lru_cache
def get_reranker() -> Reranker:
    return Reranker()