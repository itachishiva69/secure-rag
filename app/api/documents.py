from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models import User
from app.schemas.document import DocumentCreate, DocumentResponse
from app.services.document_service import (
    create_document,
    get_document_for_user,
)

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post(
    "/",
    response_model=DocumentResponse,
)
def create_document_endpoint(
    data: DocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = create_document(
        db=db,
        current_user=current_user,
        data=data,
    )

    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        storage_path=document.storage_path,
        uploaded_by=document.uploaded_by,
        status=document.status,
        created_at=document.created_at,
        department_ids=[
            department.id
            for department in document.departments
        ],
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_document_for_user(
        db=db,
        document_id=document_id,
        current_user=current_user,
    )

    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        storage_path=document.storage_path,
        uploaded_by=document.uploaded_by,
        status=document.status,
        created_at=document.created_at,
        department_ids=[
            department.id
            for department in document.departments
        ],
    )