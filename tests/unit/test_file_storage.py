import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException, UploadFile

from app.services import file_storage


def create_upload_file(
    filename: str | None,
    content: bytes,
) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(content),
        filename=filename,
    )


@pytest.fixture(autouse=True)
def force_local_storage_backend(monkeypatch):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_backend",
        "local",
    )


def create_valid_docx() -> bytes:
    buffer = io.BytesIO()

    with ZipFile(
        buffer,
        mode="w",
    ) as archive:
        archive.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
    <Default Extension="xml" ContentType="application/xml"/>
</Types>
""",
        )

        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body/>
</w:document>
""",
        )

    return buffer.getvalue()


@pytest.mark.asyncio
async def test_save_uploaded_file_generates_random_storage_name(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    first_file = create_upload_file(
        "document.txt",
        b"first document",
    )

    second_file = create_upload_file(
        "document.txt",
        b"second document",
    )

    first_path = await file_storage.save_uploaded_file(
        first_file
    )

    second_path = await file_storage.save_uploaded_file(
        second_file
    )

    first = Path(first_path)
    second = Path(second_path)

    assert first.exists()
    assert second.exists()

    assert first.name != second.name
    assert first.suffix == ".txt"
    assert second.suffix == ".txt"

    assert first.read_bytes() == b"first document"
    assert second.read_bytes() == b"second document"


@pytest.mark.asyncio
async def test_save_uploaded_file_requires_filename(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = create_upload_file(
        None,
        b"content",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Filename is required"
    )

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_save_uploaded_file_rejects_unsupported_extension(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = create_upload_file(
        "document.exe",
        b"content",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Unsupported file type. "
        "Allowed: PDF, TXT, DOCX"
    )

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_save_uploaded_file_accepts_allowed_extensions(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    test_files = {
        ".pdf": b"%PDF-1.7\nvalid pdf content",
        ".txt": b"valid UTF-8 text",
        ".docx": create_valid_docx(),
    }

    for extension, content in test_files.items():
        file = create_upload_file(
            f"document{extension}",
            content,
        )

        storage_path = await file_storage.save_uploaded_file(
            file
        )

        path = Path(storage_path)

        assert path.exists()
        assert path.suffix == extension
        assert path.read_bytes() == content


@pytest.mark.asyncio
async def test_save_uploaded_file_rejects_empty_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = create_upload_file(
        "empty.txt",
        b"",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "Uploaded file is empty"
    )

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_save_uploaded_file_rejects_oversized_file(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    monkeypatch.setattr(
        file_storage.settings,
        "max_upload_size_mb",
        1,
    )

    oversized_content = (
        b"%PDF-1.7\n"
        + b"x" * (1024 * 1024)
    )

    file = create_upload_file(
        "large.pdf",
        oversized_content,
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == (
        "File exceeds the 1 MB limit"
    )

    assert not list(tmp_path.iterdir())

def test_cloudinary_reference_helpers():
    reference = (
        "cloudinary://documents/abc123.txt"
    )

    assert file_storage.is_cloudinary_reference(
        reference
    )

    assert not file_storage.is_cloudinary_reference(
        "/app/storage/documents/abc123.txt"
    )

    assert file_storage._cloudinary_public_id(
        reference
    ) == "documents/abc123.txt"


def test_cloudinary_public_id_rejects_non_cloudinary_reference():
    with pytest.raises(ValueError) as exc_info:
        file_storage._cloudinary_public_id(
            "/app/storage/documents/test.txt"
        )

    assert exc_info.value.args[0] == (
        "Storage reference is not a Cloudinary reference"
    )


@pytest.mark.asyncio
async def test_save_uploaded_file_cloudinary(
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_backend",
        "cloudinary",
    )

    monkeypatch.setattr(
        file_storage,
        "_configure_cloudinary",
        lambda: None,
    )

    calls = []

    def fake_upload(
        source,
        **kwargs,
    ):
        calls.append(
            (
                source,
                kwargs,
            )
        )

        return {
            "asset_id": "asset-123",
        }

    monkeypatch.setattr(
        file_storage.cloudinary.uploader,
        "upload",
        fake_upload,
    )

    file = create_upload_file(
        "document.txt",
        b"cloudinary test document",
    )

    storage_reference = (
        await file_storage.save_uploaded_file(
            file
        )
    )

    assert storage_reference.startswith(
        "cloudinary://documents/"
    )
    assert storage_reference.endswith(".txt")

    assert len(calls) == 1

    _, kwargs = calls[0]

    assert kwargs == {
        "resource_type": "raw",
        "type": "authenticated",
        "public_id": storage_reference.removeprefix(
            "cloudinary://"
        ),
        "overwrite": False,
    }


def test_materialize_cloudinary_file(
    monkeypatch,
):
    reference = (
        "cloudinary://documents/test123.txt"
    )

    monkeypatch.setattr(
        file_storage,
        "_configure_cloudinary",
        lambda: None,
    )

    signed_url = (
        "https://example.test/signed-download"
    )

    download_calls = []

    def fake_private_download_url(
        **kwargs,
    ):
        download_calls.append(kwargs)
        return signed_url

    monkeypatch.setattr(
        file_storage.cloudinary.utils,
        "private_download_url",
        fake_private_download_url,
    )

    class FakeResponse:
        content = b"materialized cloudinary content"

        def raise_for_status(self):
            return None

    request_calls = []

    def fake_get(
        url,
        timeout,
    ):
        request_calls.append(
            (
                url,
                timeout,
            )
        )
        return FakeResponse()

    monkeypatch.setattr(
        file_storage.requests,
        "get",
        fake_get,
    )

    path, cleanup_required = (
        file_storage.materialize_stored_file(
            reference
        )
    )

    try:
        assert cleanup_required is True
        assert path.exists()
        assert path.suffix == ".txt"
        assert path.read_bytes() == (
            b"materialized cloudinary content"
        )

        assert download_calls == [
            {
                "public_id": "documents/test123.txt",
                "format": "txt",
                "resource_type": "raw",
                "type": "authenticated",
            }
        ]

        assert request_calls == [
            (
                signed_url,
                30,
            )
        ]

    finally:
        path.unlink(missing_ok=True)


def test_materialize_local_file(
    tmp_path,
):
    local_file = (
        tmp_path / "document.txt"
    )

    local_file.write_text(
        "local content",
        encoding="utf-8",
    )

    path, cleanup_required = (
        file_storage.materialize_stored_file(
            str(local_file)
        )
    )

    assert path == local_file
    assert cleanup_required is False


def test_delete_cloudinary_file(
    monkeypatch,
):
    reference = (
        "cloudinary://documents/delete123.txt"
    )

    monkeypatch.setattr(
        file_storage,
        "_configure_cloudinary",
        lambda: None,
    )

    calls = []

    def fake_destroy(
        public_id,
        **kwargs,
    ):
        calls.append(
            (
                public_id,
                kwargs,
            )
        )

        return {
            "result": "ok",
        }

    monkeypatch.setattr(
        file_storage.cloudinary.uploader,
        "destroy",
        fake_destroy,
    )

    file_storage.delete_stored_file(
        reference
    )

    assert calls == [
        (
            "documents/delete123.txt",
            {
                "resource_type": "raw",
                "type": "authenticated",
                "invalidate": True,
            },
        )
    ]


def test_delete_local_file(
    tmp_path,
):
    local_file = (
        tmp_path / "delete-me.txt"
    )

    local_file.write_text(
        "delete me",
        encoding="utf-8",
    )

    assert local_file.exists()

    file_storage.delete_stored_file(
        str(local_file)
    )

    assert not local_file.exists()