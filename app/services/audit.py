from sqlalchemy.orm import Session

from app.models import AuditLog, User


def record_audit_event(
    db: Session,
    *,
    user: User,
    action: str,
    resource_type: str,
    resource_id: int | None = None,
    department_id: int | None = None,
    success: bool = True,
) -> AuditLog:
    audit_log = AuditLog(
        user_id=user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        department_id=department_id,
        success=success,
    )

    db.add(audit_log)
    db.flush()

    return audit_log