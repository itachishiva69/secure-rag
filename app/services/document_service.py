from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Department, Document, DocumentDepartment, User
from app.schemas.document import DocumentCreate


def create_document(
    db: Session,
    current_user: User,
    data: DocumentCreate,
) -> Document:

    if current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    if not data.department_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one department is required",
        )

    department_ids = set(data.department_ids)

    departments = db.execute(
        select(Department).where(
            Department.id.in_(department_ids)
        )
    ).scalars().all()

    if len(departments) != len(department_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more departments do not exist",
        )

    document = Document(
        filename=data.filename,
        storage_path=data.storage_path,
        uploaded_by=current_user.id,
        status="uploaded",
    )

    db.add(document)
    db.flush()

    for department_id in department_ids:
        db.add(
            DocumentDepartment(
                document_id=document.id,
                department_id=department_id,
            )
        )

    db.commit()
    db.refresh(document)

    return document


def get_document_for_user(
    db: Session,
    document_id: int,
    current_user: User,
) -> Document:

    # Admins can access every document.
    if current_user.role.value == "admin":
        document = db.get(Document, document_id)

        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        return document

    # Non-admin users must be restricted by department.
    if current_user.department_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not assigned to a department",
        )

    query = (
        select(Document)
        .join(
            DocumentDepartment,
            Document.id == DocumentDepartment.document_id,
        )
        .where(
            Document.id == document_id,
            DocumentDepartment.department_id
            == current_user.department_id,
        )
    )

    document = db.execute(query).scalar_one_or_none()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document