import io
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile

from app.api import documents as documents_api
from app.models import (
    AuditLog,
    Department,
    Document,
    User,
)
from app.models.enums import UserRole
from app.models.document_status import DocumentStatus


def create_admin(
    db_session,
    department_id: int,
):
    user = User(
        email=(
            "upload-consistency-admin-"
            f"{uuid4().hex}@example.com"
        ),
        password_hash="test-hash",
        role=UserRole.ADMIN,
        department_id=department_id,
    )

    db_session.add(user)
    db_session.flush()

    return user


def create_department(
    db_session,
    name: str,
):
    department = Department(
        name=name
    )

    db_session.add(department)
    db_session.flush()

    return department


def create_upload(
    filename: str = "document.txt",
):
    return UploadFile(
        file=io.BytesIO(
            b"valid upload content"
        ),
        filename=filename,
    )


@pytest.mark.asyncio
async def test_db_failure_removes_stored_file(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session,
        "Upload-Consistency-DB",
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_path = (
        tmp_path
        / "stored-document.txt"
    )

    storage_path.write_bytes(
        b"valid upload content"
    )

    async def fake_save_uploaded_file(file):
        return str(storage_path)

    monkeypatch.setattr(
        documents_api,
        "save_uploaded_file",
        fake_save_uploaded_file,
    )

    def fake_create_document(**kwargs):
        raise RuntimeError(
            "simulated database failure"
        )

    monkeypatch.setattr(
        documents_api,
        "create_document",
        fake_create_document,
    )

    with pytest.raises(HTTPException) as exc_info:
        await documents_api.upload_document(
            file=create_upload(),
            department_ids=str(
                department.id
            ),
            db=db_session,
            current_user=admin,
            _=None,
        )

    assert (
        exc_info.value.status_code
        == 500
    )

    assert (
        exc_info.value.detail
        == "Failed to create document"
    )

    assert not storage_path.exists()


@pytest.mark.asyncio
async def test_queue_failure_marks_document_failed(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session,
        "Upload-Consistency-Queue",
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    storage_path = (
        tmp_path
        / "queued-document.txt"
    )

    storage_path.write_bytes(
        b"valid upload content"
    )

    async def fake_save_uploaded_file(file):
        return str(storage_path)

    monkeypatch.setattr(
        documents_api,
        "save_uploaded_file",
        fake_save_uploaded_file,
    )

    def fake_enqueue_ingestion_job(
        document_id: int,
    ):
        raise RuntimeError(
            "simulated queue failure"
        )

    monkeypatch.setattr(
        documents_api,
        "enqueue_ingestion_job",
        fake_enqueue_ingestion_job,
    )

    response_error = None

    try:
        await documents_api.upload_document(
            file=create_upload(),
            department_ids=str(
                department.id
            ),
            db=db_session,
            current_user=admin,
            _=None,
        )
    except HTTPException as exc:
        response_error = exc

    assert response_error is not None

    assert (
        response_error.status_code
        == 503
    )

    assert (
        response_error.detail
        == (
            "Document was saved, but "
            "ingestion could not be scheduled. "
            "The document has been marked "
            "as failed."
        )
    )

    document = (
        db_session.query(Document)
        .order_by(Document.id.desc())
        .first()
    )

    assert document is not None

    assert (
        document.status
        == DocumentStatus.FAILED
    )

    assert storage_path.exists()


@pytest.mark.asyncio
async def test_real_db_commit_failure_removes_stored_file(
    db_session,
    monkeypatch,
    tmp_path,
):
    department = create_department(
        db_session,
        f"Upload-Consistency-Commit-"
        f"{uuid4().hex}",
    )

    admin = create_admin(
        db_session,
        department.id,
    )

    unique_filename = (
        f"commit-failure-"
        f"{uuid4().hex}.txt"
    )

    storage_path = (
        tmp_path
        / unique_filename
    )

    storage_path.write_bytes(
        b"valid upload content"
    )

    async def fake_save_uploaded_file(file):
        return str(storage_path)

    monkeypatch.setattr(
        documents_api,
        "save_uploaded_file",
        fake_save_uploaded_file,
    )

    original_record_audit_event = (
        documents_api.record_audit_event
    )

    def failing_record_audit_event(
        db,
        *,
        user,
        action,
        resource_type,
        resource_id,
        department_id,
        success,
    ):
        original_record_audit_event(
            db,
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            department_id=department_id,
            success=success,
        )

        db.add(
            AuditLog(
                id=900000,
                user_id=user.id,
                action="forced_commit_failure",
                resource_type="test",
                resource_id=None,
                department_id=None,
                success=True,
            )
        )

        db.flush()

        db.add(
            AuditLog(
                id=900000,
                user_id=user.id,
                action="forced_commit_failure_duplicate",
                resource_type="test",
                resource_id=None,
                department_id=None,
                success=True,
            )
        )

    monkeypatch.setattr(
        documents_api,
        "record_audit_event",
        failing_record_audit_event,
    )

    with pytest.raises(HTTPException) as exc_info:
        await documents_api.upload_document(
            file=create_upload(
                filename=unique_filename
            ),
            department_ids=str(
                department.id
            ),
            db=db_session,
            current_user=admin,
            _=None,
        )

    assert (
        exc_info.value.status_code
        == 500
    )

    assert (
        exc_info.value.detail
        == "Failed to create document"
    )

    assert not storage_path.exists()

    document = (
        db_session.query(Document)
        .filter(
            Document.filename
            == unique_filename
        )
        .first()
    )

    assert document is None