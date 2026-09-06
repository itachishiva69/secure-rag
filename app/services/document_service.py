from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import (
    Department,
    Document,
    User,
)
from app.models.document_status import DocumentStatus
from app.models.enums import UserRole
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
        dict.fromkeys(
            data.department_ids
        )
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
        if department_id not in found_department_ids
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

    if document.status == DocumentStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    return document


def list_documents_for_user(
    db: Session,
    current_user: User,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Document], int]:
    if current_user.role == UserRole.ADMIN:
        base_query = (
            db.query(Document)
            .filter(
                Document.status
                != DocumentStatus.DELETING
            )
        )

        count_query = (
            db.query(
                func.count(Document.id)
            )
            .filter(
                Document.status
                != DocumentStatus.DELETING
            )
        )

    else:
        if current_user.department_id is None:
            return [], 0

        base_query = (
            db.query(Document)
            .join(Document.departments)
            .filter(
                and_(
                    Department.id
                    == current_user.department_id,
                    Document.status
                    != DocumentStatus.DELETING,
                )
            )
            .distinct()
        )

        count_query = (
            db.query(
                func.count(
                    func.distinct(
                        Document.id
                    )
                )
            )
            .join(Document.departments)
            .filter(
                and_(
                    Department.id
                    == current_user.department_id,
                    Document.status
                    != DocumentStatus.DELETING,
                )
            )
        )

    total = count_query.scalar() or 0

    documents = (
        base_query
        .order_by(
            Document.created_at.desc(),
            Document.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return documents, total


def update_document_departments(
    db: Session,
    *,
    document_id: int,
    current_user: User,
    department_ids: list[int],
) -> Document:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    requested_department_ids = list(
        dict.fromkeys(
            department_ids
        )
    )

    if not requested_department_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one department is required",
        )

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .with_for_update()
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.status == DocumentStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Document deletion is already in progress"
            ),
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
        if department_id not in found_department_ids
    ]

    if missing_department_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "One or more departments do not exist"
            ),
        )

    document.departments = departments
    document.processing_started_at = None

    if document.status != DocumentStatus.PROCESSING:
        document.status = DocumentStatus.UPLOADED

    document.deletion_started_at = None

    db.flush()

    return document


def prepare_document_reindex(
    db: Session,
    *,
    document_id: int,
    current_user: User,
) -> Document:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .with_for_update()
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if not document.departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Document has no department assignments"
            ),
        )

    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Document ingestion is already in progress"
            ),
        )

    if document.status == DocumentStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Document deletion is already in progress"
            ),
        )

    document.status = DocumentStatus.UPLOADED
    document.processing_started_at = None
    document.deletion_started_at = None

    db.flush()

    return document


def prepare_document_delete(
    db: Session,
    *,
    document_id: int,
    current_user: User,
) -> Document:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    document = (
        db.query(Document)
        .filter(
            Document.id == document_id
        )
        .with_for_update()
        .first()
    )

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if document.status == DocumentStatus.PROCESSING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Document ingestion is currently in progress"
            ),
        )

    if document.status == DocumentStatus.DELETING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Document deletion is already in progress"
            ),
        )

    document.status = DocumentStatus.DELETING
    document.processing_started_at = None
    document.deletion_started_at = datetime.now(
        timezone.utc
    )

    db.flush()

    return document