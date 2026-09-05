from app.models import User
from app.models.enums import UserRole


def get_allowed_department_ids(
    current_user: User,
) -> list[int] | None:
    """
    Return the department IDs the user is authorized to access.

    None means unrestricted access.
    An empty list means the user has no department access.
    """

    if current_user.role == UserRole.ADMIN:
        return None

    if current_user.department_id is None:
        return []

    return [current_user.department_id]