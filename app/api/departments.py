from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.db.database import get_db
from app.models import Department
from app.models import User
from app.schemas.department import DepartmentResponse


router = APIRouter(
    prefix="/departments",
    tags=["Departments"],
)


@router.get(
    "/",
    response_model=list[DepartmentResponse],
)
def list_departments(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = db.execute(
        select(Department).order_by(Department.name)
    )

    return result.scalars().all()