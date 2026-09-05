from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.models import Department, Document
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
from app.models import User
from app.schemas.document import DocumentCreate


def create_document(
    db: Session,
    current_user: User,
    data: DocumentCreate,
) -> Document:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    requested_department_ids = list(
        dict.fromkeys(data.department_ids)
    )

    if not requested_department_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one department is required",
        )

    departments = (
        db.query(Department)
        .filter(
            Department.id.in_(
                requested_department_ids
            )
        )
        .all()
    )

    found_department_ids = {
        department.id
        for department in departments
    }

    missing_department_ids = [
        department_id
        for department_id in requested_department_ids
        if department_id
        not in found_department_ids
    ]

    if missing_department_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "One or more departments do not exist"
            ),
        )

    document = Document(
        filename=data.filename,
        storage_path=data.storage_path,
        uploaded_by=current_user.id,
        status=DocumentStatus.UPLOADED,
    )

    document.departments = departments

    db.add(document)

    # Flush so the document ID and relationship
    # rows are created, but do NOT commit here.
    #
    # The API layer owns the transaction boundary.
    db.flush()

    return document


def get_document_for_user(
    db: Session,
    document_id: int,
    current_user: User,
) -> Document:
    if current_user.role == UserRole.ADMIN:
        document = (
            db.query(Document)
            .filter(
                Document.id == document_id
            )
            .first()
        )
    else:
        if current_user.department_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        document = (
            db.query(Document)
            .join(Document.departments)
            .filter(
                and_(
                    Document.id == document_id,
                    Department.id
                    == current_user.department_id,
                )
            )
            .first()
        )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document