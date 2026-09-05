from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models import User
from app.schemas.query import (
    RetrievalRequest,
    RetrievalResponse,
    RetrievedChunk,
)
from app.services.retrieval import retrieve_documents


router = APIRouter(
    prefix="/query",
    tags=["Query"],
)


@router.post(
    "/",
    response_model=RetrievalResponse,
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

    chunks = []

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

    return RetrievalResponse(
        query=request.query,
        results=chunks,
    )