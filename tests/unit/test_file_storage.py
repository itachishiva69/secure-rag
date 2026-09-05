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