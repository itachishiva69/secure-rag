from dataclasses import dataclass
from functools import lru_cache
import math

from fastembed.rerank.cross_encoder import TextCrossEncoder

from app.core.config import get_settings
from app.schemas.query import RetrievedChunk


DEFAULT_RERANKER_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"


class RerankerError(Exception):
    """Raised when reranking cannot be completed."""


@dataclass(frozen=True)
class RerankedChunk:
    chunk: RetrievedChunk
    score: float


class Reranker:
    def __init__(
        self,
        model_name: str | None = None,
    ):
        if model_name is None:
            model_name = (
                get_settings().reranker_model
            )

        try:
            self.model = TextCrossEncoder(
                model_name=model_name,
                lazy_load=True,
                threads=1,
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

        documents = [
            chunk.text
            for chunk in chunks
        ]

        try:
            scores = list(
                self.model.rerank(
                    query=query,
                    documents=documents,
                    batch_size=min(
                        len(documents),
                        32,
                    ),
                )
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

        ranked: list[RerankedChunk] = []

        try:
            for chunk, score in zip(
                chunks,
                scores,
            ):
                numeric_score = float(score)

                if not math.isfinite(
                    numeric_score
                ):
                    raise ValueError(
                        "Reranker returned a "
                        "non-finite score"
                    )

                ranked.append(
                    RerankedChunk(
                        chunk=chunk,
                        score=numeric_score,
                    )
                )
        except Exception as exc:
            raise RerankerError(
                "Reranker returned invalid scores"
            ) from exc

        ranked.sort(
            key=lambda result: result.score,
            reverse=True,
        )

        return ranked[:limit]


@lru_cache
def get_reranker() -> Reranker:
    return Reranker()