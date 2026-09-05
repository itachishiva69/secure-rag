from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_current_user
from app.models import User
from app.schemas.query import (
    QueryResponse,
    QuerySource,
    RetrievedChunk,
    RetrievalRequest,
)
from app.services.context import build_context
from app.services.generation import GenerationService
from app.services.llm_provider import (
    LLMProviderError,
    get_llm_provider,
)
from app.services.retrieval import retrieve_documents


router = APIRouter(
    prefix="/query",
    tags=["Query"],
)


@router.post(
    "/",
    response_model=QueryResponse,
)
def query_documents(
    request: RetrievalRequest,
    current_user: User = Depends(get_current_user),
):
    results = retrieve_documents(
        query=request.query,
        current_user=current_user,
        limit=request.limit,
    )

    chunks: list[RetrievedChunk] = []

    if results:
        for result in results.points:
            payload = result.payload or {}

            chunks.append(
                RetrievedChunk(
                    document_id=payload["document_id"],
                    filename=payload["filename"],
                    chunk_index=payload["chunk_index"],
                    department_ids=payload["department_ids"],
                    text=payload["text"],
                )
            )

    context = build_context(chunks)

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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The language model provider is temporarily unavailable.",
        ) from exc

    sources = [
        QuerySource(
            document_id=source.document_id,
            filename=source.filename,
            chunk_index=source.chunk_index,
        )
        for source in context.sources
    ]

    return QueryResponse(
        query=request.query,
        answer=generation_result.answer,
        sources=sources,
    )