import logging
from functools import lru_cache
from time import perf_counter

from app.rag.embeddings import get_embedding_service
from app.rag.reranker import (
    RerankerError,
    get_reranker,
)


logger = logging.getLogger("app.model_warmup")


@lru_cache
def warm_models() -> bool:
    """
    Load the query-time ML models once during application startup.

    The embedding model is required because every query depends on it.
    The reranker remains optional to preserve the existing query behavior:
    if it cannot be loaded, query handling can continue without reranking.
    """
    started_at = perf_counter()

    try:
        embedding_service = get_embedding_service()
        embedding_dimension = embedding_service.dimension
    except Exception:
        logger.exception(
            "embedding_model_warmup_failed"
        )
        raise

    embedding_duration_ms = round(
        (perf_counter() - started_at) * 1000,
        2,
    )

    logger.info(
        "embedding_model_warmed",
        extra={
            "embedding_dimension": embedding_dimension,
            "duration_ms": embedding_duration_ms,
        },
    )

    reranker_started_at = perf_counter()

    try:
        get_reranker()
    except RerankerError:
        logger.exception(
            "reranker_model_warmup_failed"
        )
    else:
        reranker_duration_ms = round(
            (perf_counter() - reranker_started_at) * 1000,
            2,
        )

        logger.info(
            "reranker_model_warmed",
            extra={
                "duration_ms": reranker_duration_ms,
            },
        )

    total_duration_ms = round(
        (perf_counter() - started_at) * 1000,
        2,
    )

    logger.info(
        "query_models_warmed",
        extra={
            "duration_ms": total_duration_ms,
        },
    )

    return True
