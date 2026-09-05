from pydantic import ValidationError

from app.models import User
from app.rag.qdrant_store import search
from app.rag.reranker import Reranker
from app.schemas.query import RetrievedChunk
from app.services.authorization import get_allowed_department_ids


RERANKER_CANDIDATE_LIMIT = 10


def _is_authorized_chunk(
    chunk: RetrievedChunk,
    allowed_department_ids: list[int] | None,
) -> bool:
    if allowed_department_ids is None:
        return True

    if not allowed_department_ids:
        return False

    return bool(
        set(chunk.department_ids)
        & set(allowed_department_ids)
    )


def retrieve_documents(
    *,
    query: str,
    current_user: User,
    limit: int = 5,
    reranker: Reranker | None = None,
):
    allowed_department_ids = get_allowed_department_ids(
        current_user
    )

    # A non-admin user without a department has no
    # authorized documents. Return before touching
    # Qdrant or the reranker.
    if (
        allowed_department_ids is not None
        and not allowed_department_ids
    ):
        return []

    candidate_limit = limit

    if reranker is not None:
        candidate_limit = max(
            limit,
            RERANKER_CANDIDATE_LIMIT,
        )

    results = search(
        query=query,
        allowed_department_ids=allowed_department_ids,
        limit=candidate_limit,
    )

    if not results or not getattr(
        results,
        "points",
        None,
    ):
        return results

    candidates = []

    for point in results.points:
        payload = point.payload or {}

        try:
            chunk = RetrievedChunk.model_validate(
                payload
            )
        except ValidationError:
            continue

        if not _is_authorized_chunk(
            chunk,
            allowed_department_ids,
        ):
            continue

        candidates.append(
            (
                point,
                chunk,
            )
        )

    if not candidates:
        results.points = []
        return results

    if reranker is None:
        results.points = [
            point
            for point, _ in candidates
        ]
        return results

    reranked = reranker.rerank(
        query=query,
        chunks=[
            chunk
            for _, chunk in candidates
        ],
        limit=limit,
    )

    points_by_chunk = {
        (
            chunk.document_id,
            chunk.chunk_index,
        ): point
        for point, chunk in candidates
    }

    reranked_points = []

    for result in reranked:
        key = (
            result.chunk.document_id,
            result.chunk.chunk_index,
        )

        point = points_by_chunk.get(key)

        if point is not None:
            reranked_points.append(point)

    results.points = reranked_points

    return results