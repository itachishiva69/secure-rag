from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.document import (
    DocumentCreate,
    DocumentResponse,
)
from app.services.document_service import (
    create_document,
    get_document_for_user,
)
from app.services.file_storage import save_uploaded_file
from app.services.queue import get_ingestion_queue
from app.services.jobs import ingest_document_job


router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


@router.post(
    "/upload",
    response_model=DocumentResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    department_ids: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )

    try:
        parsed_department_ids = [
            int(value.strip())
            for value in department_ids.split(",")
            if value.strip()
        ]
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="department_ids must contain integers",
        )

    if not parsed_department_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one department is required",
        )

    storage_path = await save_uploaded_file(file)

    document = create_document(
        db=db,
        current_user=current_user,
        data=DocumentCreate(
            filename=file.filename,
            storage_path=storage_path,
            department_ids=parsed_department_ids,
        ),
    )

    queue = get_ingestion_queue()

    queue.enqueue(
        ingest_document_job,
        document.id,
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