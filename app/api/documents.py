from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.database import get_db
from app.models import User
from app.models.enums import UserRole
from app.schemas.document import (
    DocumentCreate,
    DocumentDepartmentUpdate,
    DocumentListResponse,
    DocumentResponse,
)
from app.services.audit import record_audit_event
from app.services.document_service import (
    create_document,
    get_document_for_user,
    list_documents_for_user,
    prepare_document_delete,
    prepare_document_reindex,
    update_document_departments,
)
from app.services.file_storage import (
    save_uploaded_file,
)
from app.services.outbox import (
    create_delete_outbox_event,
    create_ingestion_outbox_event,
)
from app.services.rate_limit import (
    RateLimitError,
    RateLimitExceeded,
    RateLimiter,
    get_redis,
)


settings = get_settings()

router = APIRouter(
    prefix="/documents",
    tags=["Documents"],
)


def get_upload_rate_limiter() -> RateLimiter:
    return RateLimiter(
        redis=get_redis(),
        requests=settings.upload_rate_limit_requests,
        window_seconds=(
            settings.upload_rate_limit_window_seconds
        ),
        key_prefix="secure-rag:rate-limit:upload",
    )


def enforce_upload_rate_limit(
    current_user: User = Depends(
        get_current_user
    ),
) -> None:
    rate_limiter = (
        get_upload_rate_limiter()
    )

    try:
        rate_limiter.check(
            subject=str(
                current_user.id
            )
        )

    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_429_TOO_MANY_REQUESTS
            ),
            detail=(
                "Too many upload requests. "
                "Please try again later."
            ),
            headers={
                "Retry-After": str(
                    exc.window_seconds
                ),
            },
        ) from exc

    except RateLimitError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "The request protection service "
                "is temporarily unavailable."
            ),
        ) from exc


def delete_stored_file(
    storage_path: str,
) -> None:
    Path(
        storage_path
    ).unlink(
        missing_ok=True
    )


def build_document_response(
    document,
) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        storage_path=document.storage_path,
        uploaded_by=document.uploaded_by,
        status=document.status.value,
        created_at=document.created_at,
        department_ids=[
            department.id
            for department in document.departments
        ],
    )


@router.post(
    "/upload",
    response_model=DocumentResponse,
)
async def upload_document(
    file: UploadFile = File(...),
    department_ids: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
    _: None = Depends(
        enforce_upload_rate_limit
    ),
):
    if current_user.role != (
        UserRole.ADMIN
    ):
        raise HTTPException(
            status_code=(
                status.HTTP_403_FORBIDDEN
            ),
            detail="Admin privileges required",
        )

    try:
        parsed_department_ids = [
            int(value.strip())
            for value in department_ids.split(",")
            if value.strip()
        ]

    except ValueError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "department_ids must contain integers"
            ),
        ) from exc

    if not parsed_department_ids:
        raise HTTPException(
            status_code=(
                status.HTTP_400_BAD_REQUEST
            ),
            detail=(
                "At least one department is required"
            ),
        )

    storage_path = await save_uploaded_file(
        file
    )

    try:
        document = create_document(
            db=db,
            current_user=current_user,
            data=DocumentCreate(
                filename=file.filename,
                storage_path=storage_path,
                department_ids=(
                    parsed_department_ids
                ),
            ),
        )

        create_ingestion_outbox_event(
            db=db,
            document_id=document.id,
        )

        record_audit_event(
            db,
            user=current_user,
            action="document_upload",
            resource_type="document",
            resource_id=document.id,
            department_id=(
                parsed_department_ids[0]
                if len(
                    parsed_department_ids
                ) == 1
                else None
            ),
            success=True,
        )

        db.commit()

    except Exception as exc:
        db.rollback()

        delete_stored_file(
            storage_path
        )

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail="Failed to create document",
        ) from exc

    return build_document_response(
        document
    )


@router.get(
    "",
    response_model=DocumentListResponse,
)
def list_documents_endpoint(
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    documents, total = (
        list_documents_for_user(
            db=db,
            current_user=current_user,
            limit=limit,
            offset=offset,
        )
    )

    record_audit_event(
        db,
        user=current_user,
        action="document_list",
        resource_type="document",
        resource_id=None,
        department_id=(
            current_user.department_id
        ),
        success=True,
    )

    db.commit()

    return DocumentListResponse(
        items=[
            build_document_response(
                document
            )
            for document in documents
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
)
def get_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    try:
        document = get_document_for_user(
            db=db,
            document_id=document_id,
            current_user=current_user,
        )

    except HTTPException:
        record_audit_event(
            db,
            user=current_user,
            action="document_access",
            resource_type="document",
            resource_id=document_id,
            department_id=(
                current_user.department_id
            ),
            success=False,
        )

        db.commit()
        raise

    record_audit_event(
        db,
        user=current_user,
        action="document_access",
        resource_type="document",
        resource_id=document.id,
        department_id=(
            current_user.department_id
        ),
        success=True,
    )

    db.commit()

    return build_document_response(
        document
    )


@router.patch(
    "/{document_id}/departments",
    response_model=DocumentResponse,
)
def update_document_departments_endpoint(
    document_id: int,
    data: DocumentDepartmentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    try:
        document = (
            update_document_departments(
                db=db,
                document_id=document_id,
                current_user=current_user,
                department_ids=(
                    data.department_ids
                ),
            )
        )

        create_ingestion_outbox_event(
            db=db,
            document_id=document.id,
        )

        department_id = (
            data.department_ids[0]
            if len(
                data.department_ids
            ) == 1
            else None
        )

        record_audit_event(
            db,
            user=current_user,
            action="document_departments_update",
            resource_type="document",
            resource_id=document.id,
            department_id=department_id,
            success=True,
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Failed to update document departments"
            ),
        ) from exc

    return build_document_response(
        document
    )


@router.post(
    "/{document_id}/reindex",
    response_model=DocumentResponse,
)
def reindex_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    try:
        document = prepare_document_reindex(
            db=db,
            document_id=document_id,
            current_user=current_user,
        )

        create_ingestion_outbox_event(
            db=db,
            document_id=document.id,
        )

        record_audit_event(
            db,
            user=current_user,
            action="document_reindex",
            resource_type="document",
            resource_id=document.id,
            department_id=(
                document.departments[0].id
                if len(
                    document.departments
                ) == 1
                else None
            ),
            success=True,
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_500_INTERNAL_SERVER_ERROR
            ),
            detail=(
                "Failed to schedule document reindex"
            ),
        ) from exc

    return build_document_response(
        document
    )


@router.delete(
    "/{document_id}",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentResponse,
)
def delete_document_endpoint(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        get_current_user
    ),
):
    try:
        document = prepare_document_delete(
            db=db,
            document_id=document_id,
            current_user=current_user,
        )

        create_delete_outbox_event(
            db=db,
            document_id=document.id,
        )

        record_audit_event(
            db,
            user=current_user,
            action="document_delete",
            resource_type="document",
            resource_id=document.id,
            department_id=(
                document.departments[0].id
                if len(
                    document.departments
                ) == 1
                else None
            ),
            success=True,
        )

        db.commit()

    except HTTPException:
        db.rollback()
        raise

    except Exception as exc:
        db.rollback()

        raise HTTPException(
            status_code=(
                status.HTTP_503_SERVICE_UNAVAILABLE
            ),
            detail=(
                "Document deletion could not be completed safely. "
                "Please try again."
            ),
        ) from exc

    return build_document_response(
        document
    )