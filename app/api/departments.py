from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models import Department, User
from app.schemas.department import (
    DepartmentCreate,
    DepartmentResponse,
)
from app.services.admin_service import (
    create_department,
)
from app.services.audit import record_audit_event


router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
)


@router.post(
    "/",
    response_model=DepartmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_department_endpoint(
    data: DepartmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        department = create_department(
            db=db,
            name=data.name,
        )

        record_audit_event(
            db,
            user=current_user,
            action="department_create",
            resource_type="department",
            resource_id=department.id,
            department_id=department.id,
            success=True,
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create department",
        ) from exc

    return department


@router.get(
    "/",
    response_model=list[DepartmentResponse],
)
def list_departments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    result = db.execute(
        select(Department).order_by(
            Department.name
        )
    )

    departments = result.scalars().all()

    record_audit_event(
        db,
        user=current_user,
        action="department_list",
        resource_type="department",
        resource_id=None,
        department_id=None,
        success=True,
    )

    db.commit()

    return departments