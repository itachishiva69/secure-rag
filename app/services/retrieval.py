from pydantic import ValidationError
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Department, Document, User
from app.models.document_status import DocumentStatus
from app.rag.qdrant_store import search
from app.rag.reranker import Reranker
from app.schemas.query import RetrievedChunk
from app.services.authorization import get_allowed_department_ids


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


def _get_authorized_document_ids(
    db: Session,
    *,
    current_user: User,
    document_ids: set[int],
) -> set[int]:
    if not document_ids:
        return set()

    query = (
        db.query(Document.id)
        .filter(
            Document.id.in_(document_ids),
            Document.status != DocumentStatus.DELETING,
        )
    )

    allowed_department_ids = get_allowed_department_ids(
        current_user
    )

    if allowed_department_ids is None:
        rows = query.all()
    elif not allowed_department_ids:
        return set()
    else:
        rows = (
            query
            .join(Document.departments)
            .filter(
                Department.id.in_(
                    allowed_department_ids
                )
            )
            .distinct()
            .all()
        )

    return {
        document_id
        for (document_id,) in rows
    }


def _filter_authorized_results(
    db: Session,
    *,
    current_user: User,
    points,
):
    if not points:
        return []

    document_ids = set()

    for point in points:
        payload = point.payload or {}

        document_id = payload.get(
            "document_id"
        )

        if isinstance(document_id, int):
            document_ids.add(
                document_id
            )

    authorized_document_ids = (
        _get_authorized_document_ids(
            db,
            current_user=current_user,
            document_ids=document_ids,
        )
    )

    return [
        point
        for point in points
        if isinstance(
            (point.payload or {}).get(
                "document_id"
            ),
            int,
        )
        and (
            point.payload["document_id"]
            in authorized_document_ids
        )
    ]


def retrieve_documents(
    *,
    db: Session,
    query: str,
    current_user: User,
    limit: int = 5,
    reranker: Reranker | None = None,
):
    allowed_department_ids = get_allowed_department_ids(
        current_user
    )

    if (
        allowed_department_ids is not None
        and not allowed_department_ids
    ):
        return []

    candidate_limit = limit

    if reranker is not None:
        candidate_limit = max(
            limit,
            get_settings().reranker_candidate_limit,
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

    authorized_points = _filter_authorized_results(
        db,
        current_user=current_user,
        points=[
            point
            for point, _ in candidates
        ],
    )

    authorized_point_ids = {
        id(point)
        for point in authorized_points
    }

    candidates = [
        (
            point,
            chunk,
        )
        for point, chunk in candidates
        if id(point) in authorized_point_ids
    ]

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
            reranked_points.append(
                point
            )

    results.points = reranked_points

    return results