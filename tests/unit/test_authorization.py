from types import SimpleNamespace

from app.models.enums import UserRole
from app.services.authorization import get_allowed_department_ids


def test_admin_has_unrestricted_access():
    user = SimpleNamespace(
        role=UserRole.ADMIN,
        department_id=None,
    )

    assert get_allowed_department_ids(user) is None


def test_user_gets_only_their_department():
    user = SimpleNamespace(
        role=UserRole.USER,
        department_id=3,
    )

    assert get_allowed_department_ids(user) == [3]


def test_user_without_department_has_no_access():
    user = SimpleNamespace(
        role=UserRole.USER,
        department_id=None,
    )

    assert get_allowed_department_ids(user) == []