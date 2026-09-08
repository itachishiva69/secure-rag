import json
import logging
from collections.abc import Iterator
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.models import ConversationMessageRole, User
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
from app.services.conversation import (
    add_conversation_message,
    get_owned_conversation,
    get_recent_user_messages,
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


def _load_conversation_context(
    db: Session,
    *,
    request: RetrievalRequest,
    current_user: User,
) -> tuple[object | None, list[str]]:
    if request.conversation_id is None:
        return None, []

    conversation = get_owned_conversation(
        db,
        conversation_id=request.conversation_id,
        current_user=current_user,
    )

    previous_user_messages = get_recent_user_messages(
        db,
        conversation=conversation,
        limit=8,
    )

    return conversation, previous_user_messages


def _retrieve_context(
    *,
    db: Session,
    request: RetrievalRequest,
    current_user: User,
    reranker: Reranker | None,
) -> ContextResult:
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
        return build_context(chunks)

    return build_empty_context()


def _build_sources(
    context: ContextResult,
) -> list[QuerySource]:
    return [
        QuerySource(
            document_id=source.document_id,
            filename=source.filename,
            chunk_index=source.chunk_index,
        )
        for source in context.sources
    ]


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
    conversation, previous_user_messages = (
        _load_conversation_context(
            db,
            request=request,
            current_user=current_user,
        )
    )

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
            "conversation_id": (
                conversation.id
                if conversation is not None
                else None
            ),
            "conversation_history_user_message_count": (
                len(previous_user_messages)
            ),
        },
    )

    context = _retrieve_context(
        db=db,
        request=request,
        current_user=current_user,
        reranker=reranker,
    )

    logger.info(
        "query_retrieval_completed",
        extra={
            "user_id": current_user.id,
            "valid_chunk_count": len(
                context.sources
            ),
            "context_source_count": len(
                context.sources
            ),
            "conversation_id": (
                conversation.id
                if conversation is not None
                else None
            ),
        },
    )

    if context.text:
        generation_service = GenerationService(
            provider=get_llm_provider()
        )
    else:
        generation_service = GenerationService()

    try:
        if conversation is not None:
            generation_result = (
                generation_service.generate_conversational_answer(
                    query=request.query,
                    context=context,
                    previous_user_messages=(
                        previous_user_messages
                    ),
                )
            )

        else:
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
                "conversation_id": (
                    conversation.id
                    if conversation is not None
                    else None
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

    sources = _build_sources(context)

    if conversation is not None:
        add_conversation_message(
            db,
            conversation=conversation,
            role=ConversationMessageRole.USER,
            content=request.query,
        )

        add_conversation_message(
            db,
            conversation=conversation,
            role=ConversationMessageRole.ASSISTANT,
            content=generation_result.answer,
        )

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
            "conversation_id": (
                conversation.id
                if conversation is not None
                else None
            ),
        },
    )

    return QueryResponse(
        query=request.query,
        answer=generation_result.answer,
        sources=sources,
        conversation_id=(
            conversation.id
            if conversation is not None
            else None
        ),
    )


def _sse_event(
    event: str,
    data: dict,
) -> str:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    )


@router.post(
    "/stream",
)
def stream_query_documents(
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
    conversation, previous_user_messages = (
        _load_conversation_context(
            db,
            request=request,
            current_user=current_user,
        )
    )

    context = _retrieve_context(
        db=db,
        request=request,
        current_user=current_user,
        reranker=reranker,
    )

    if context.text:
        generation_service = GenerationService(
            provider=get_llm_provider()
        )
    else:
        generation_service = GenerationService()

    conversation_id = (
        conversation.id
        if conversation is not None
        else None
    )

    sources = _build_sources(context)

    def event_stream() -> Iterator[str]:
        answer_parts: list[str] = []

        logger.info(
            "query_stream_started",
            extra={
                "user_id": current_user.id,
                "conversation_id": conversation_id,
                "source_count": len(sources),
            },
        )

        yield _sse_event(
            "start",
            {
                "conversation_id": conversation_id,
                "sources": [
                    {
                        "document_id": source.document_id,
                        "filename": source.filename,
                        "chunk_index": source.chunk_index,
                    }
                    for source in sources
                ],
            },
        )

        try:
            if conversation is not None:
                stream = (
                    generation_service.stream_conversational_answer(
                        query=request.query,
                        context=context,
                        previous_user_messages=(
                            previous_user_messages
                        ),
                    )
                )

            else:
                stream = generation_service.stream_answer(
                    query=request.query,
                    context=context,
                )

            for chunk in stream:
                if not chunk:
                    continue

                answer_parts.append(chunk)

                yield _sse_event(
                    "token",
                    {
                        "text": chunk,
                    },
                )

            answer = "".join(
                answer_parts
            ).strip()

            if not answer:
                raise LLMProviderError(
                    "LLM provider returned empty content"
                )

            if conversation is not None:
                add_conversation_message(
                    db,
                    conversation=conversation,
                    role=ConversationMessageRole.USER,
                    content=request.query,
                )

                add_conversation_message(
                    db,
                    conversation=conversation,
                    role=ConversationMessageRole.ASSISTANT,
                    content=answer,
                )

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

            yield _sse_event(
                "done",
                {
                    "conversation_id": conversation_id,
                    "answer": answer,
                    "sources": [
                        {
                            "document_id": source.document_id,
                            "filename": source.filename,
                            "chunk_index": source.chunk_index,
                        }
                        for source in sources
                    ],
                },
            )

            logger.info(
                "query_stream_completed",
                extra={
                    "user_id": current_user.id,
                    "conversation_id": conversation_id,
                    "source_count": len(sources),
                    "answer_length": len(answer),
                },
            )

        except LLMProviderError:
            db.rollback()

            logger.exception(
                "query_stream_llm_provider_failed",
                extra={
                    "user_id": current_user.id,
                    "conversation_id": conversation_id,
                },
            )

            yield _sse_event(
                "error",
                {
                    "code": "llm_provider_unavailable",
                    "detail": (
                        "The language model provider "
                        "is temporarily unavailable."
                    ),
                },
            )

        except GeneratorExit:
            db.rollback()

            logger.info(
                "query_stream_client_disconnected",
                extra={
                    "user_id": current_user.id,
                    "conversation_id": conversation_id,
                    "partial_answer_length": len(
                        "".join(answer_parts)
                    ),
                },
            )

            raise

        except Exception:
            db.rollback()

            logger.exception(
                "query_stream_failed",
                extra={
                    "user_id": current_user.id,
                    "conversation_id": conversation_id,
                },
            )

            yield _sse_event(
                "error",
                {
                    "code": "stream_failed",
                    "detail": (
                        "The query stream "
                        "could not be completed."
                    ),
                },
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
