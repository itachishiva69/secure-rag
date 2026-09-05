from dataclasses import dataclass
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.schemas.query import RetrievedChunk


RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"


class RerankerError(Exception):
    """Raised when reranking cannot be completed."""


@dataclass(frozen=True)
class RerankedChunk:
    chunk: RetrievedChunk
    score: float


class Reranker:
    def __init__(
        self,
        model_name: str = RERANKER_MODEL,
    ):
        try:
            self.model = CrossEncoder(
                model_name,
                device="cpu",
            )
        except Exception as exc:
            raise RerankerError(
                "Reranker model could not be loaded"
            ) from exc

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

        try:
            scores = self.model.predict(
                pairs,
                show_progress_bar=False,
            )
        except Exception as exc:
            raise RerankerError(
                "Reranker inference failed"
            ) from exc

        if len(scores) != len(chunks):
            raise RerankerError(
                "Reranker returned an unexpected "
                "number of scores"
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