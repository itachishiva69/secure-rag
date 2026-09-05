from app.models import User
from app.rag.qdrant_store import search
from app.services.authorization import get_allowed_department_ids


def retrieve_documents(
    *,
    query: str,
    current_user: User,
    limit: int = 5,
):
    allowed_department_ids = get_allowed_department_ids(
        current_user
    )

    return search(
        query=query,
        allowed_department_ids=allowed_department_ids,
        limit=limit,
    )