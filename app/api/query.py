import logging
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.models import User
from app.rag.qdrant_store import QdrantStoreError
from app.rag.reranker import (
    Reranker,
    RerankerError,
    get_reranker,
)
from app.schemas.query import (
    QueryResponse,
    QuerySource,
    RetrievedChunk,
    RetrievalRequest,
)
from app.services.audit import record_audit_event
from app.services.context import (
    ContextResult,
    build_context,
)
from app.services.generation import GenerationService
from app.services.llm_provider import (
    LLMProviderError,
    get_llm_provider,
)
from app.services.rate_limit import (
    RateLimitError,
    RateLimitExceeded,
    RateLimiter,
    get_redis,
)
from app.services.retrieval import retrieve_documents


logger = logging.getLogger(__name__)

settings = get_settings()

router = APIRouter(
    prefix="/query",
    tags=["Query"],
)


def get_query_rate_limiter() -> RateLimiter:
    return RateLimiter(
        redis=get_redis(),
        requests=settings.query_rate_limit_requests,
        window_seconds=(
            settings.query_rate_limit_window_seconds
        ),
        key_prefix="secure-rag:rate-limit:query",
    )


def enforce_query_rate_limit(
    current_user: User = Depends(
        get_current_user
    ),
) -> None:
    rate_limiter = get_query_rate_limiter()

    try:
        rate_limiter.check(
            subject=str(
                current_user.id
            )
        )

    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Too many query requests. "
                "Please try again later."
            ),
            headers={
                "Retry-After": str(
                    exc.window_seconds
                ),
            },
        ) from exc

    except RateLimitError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The request protection service "
                "is temporarily unavailable."
            ),
        ) from exc


@lru_cache
def get_query_reranker() -> Reranker | None:
    try:
        return get_reranker()
    except RerankerError:
        logger.exception(
            "query_reranker_unavailable"
        )
        return None


def parse_retrieved_chunk(
    payload: dict,
) -> RetrievedChunk | None:
    try:
        return RetrievedChunk.model_validate(
            payload
        )
    except ValidationError:
        return None


def build_empty_context() -> ContextResult:
    return ContextResult(
        text="",
        sources=[],
    )


@router.post(
    "/",
    response_model=QueryResponse,
)
def query_documents(
    request: RetrievalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
    _: None = Depends(
        enforce_query_rate_limit
    ),
    reranker: Reranker | None = Depends(
        get_query_reranker
    ),
):
    logger.info(
        "query_started",
        extra={
            "user_id": current_user.id,
            "user_role": current_user.role.value,
            "department_id": (
                current_user.department_id
            ),
            "requested_limit": request.limit,
            "reranker_enabled": (
                reranker is not None
            ),
        },
    )

    try:
        results = retrieve_documents(
            db=db,
            query=request.query,
            current_user=current_user,
            limit=request.limit,
            reranker=reranker,
        )

    except QdrantStoreError as exc:
        logger.exception(
            "query_qdrant_failed",
            extra={
                "user_id": current_user.id,
                "requested_limit": request.limit,
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The document retrieval service "
                "is temporarily unavailable."
            ),
        ) from exc

    except RerankerError as exc:
        logger.exception(
            "query_reranking_failed",
            extra={
                "user_id": current_user.id,
                "requested_limit": request.limit,
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The document reranking service "
                "is temporarily unavailable."
            ),
        ) from exc

    retrieved_point_count = 0

    if results:
        retrieved_point_count = len(
            results.points
        )

    chunks: list[RetrievedChunk] = []

    if results:
        for result in results.points:
            payload = result.payload or {}

            chunk = parse_retrieved_chunk(
                payload
            )

            if chunk is None:
                continue

            chunks.append(chunk)

    if chunks:
        context = build_context(chunks)
    else:
        context = build_empty_context()

    logger.info(
        "query_retrieval_completed",
        extra={
            "user_id": current_user.id,
            "retrieved_point_count": (
                retrieved_point_count
            ),
            "valid_chunk_count": len(chunks),
            "context_source_count": len(
                context.sources
            ),
        },
    )

    if context.text:
        generation_service = GenerationService(
            provider=get_llm_provider(),
        )
    else:
        generation_service = GenerationService()

    try:
        generation_result = (
            generation_service.generate_answer(
                query=request.query,
                context=context,
            )
        )

    except LLMProviderError as exc:
        logger.exception(
            "query_llm_provider_failed",
            extra={
                "user_id": current_user.id,
                "context_source_count": len(
                    context.sources
                ),
            },
        )

        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY
            ),
            detail=(
                "The language model provider "
                "is temporarily unavailable."
            ),
        ) from exc

    sources = [
        QuerySource(
            document_id=source.document_id,
            filename=source.filename,
            chunk_index=source.chunk_index,
        )
        for source in context.sources
    ]

    record_audit_event(
        db,
        user=current_user,
        action="query",
        resource_type="query",
        department_id=(
            current_user.department_id
        ),
    )

    db.commit()

    logger.info(
        "query_completed",
        extra={
            "user_id": current_user.id,
            "source_count": len(sources),
            "answer_generated": True,
        },
    )

    return QueryResponse(
        query=request.query,
        answer=generation_result.answer,
        sources=sources,
    )