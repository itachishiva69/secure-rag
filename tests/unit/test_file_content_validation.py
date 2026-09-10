import io
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException, UploadFile

from app.services import file_storage


@pytest.fixture(autouse=True)
def force_local_storage_backend(monkeypatch):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_backend",
        "local",
    )


def make_upload(
    filename: str,
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
async def test_valid_pdf_content_is_accepted(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "document.pdf",
        b"%PDF-1.7\nvalid pdf content",
    )

    result = await file_storage.save_uploaded_file(
        file
    )

    path = Path(result)

    assert path.exists()
    assert path.suffix == ".pdf"
    assert path.read_bytes().startswith(b"%PDF-")

    path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_valid_docx_content_is_accepted(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "document.docx",
        create_valid_docx(),
    )

    result = await file_storage.save_uploaded_file(
        file
    )

    path = Path(result)

    assert path.exists()
    assert path.suffix == ".docx"

    path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_valid_txt_content_is_accepted(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "document.txt",
        b"This is valid UTF-8 text.",
    )

    result = await file_storage.save_uploaded_file(
        file
    )

    path = Path(result)

    assert path.exists()
    assert path.suffix == ".txt"

    path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_pdf_extension_with_non_pdf_content_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "malicious.pdf",
        b"This is not a PDF file",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "File content does not match "
        "the filename extension"
    )

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_docx_extension_with_non_docx_content_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "malicious.docx",
        b"This is not a DOCX file",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "File content does not match "
        "the filename extension"
    )

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_corrupt_zip_with_docx_extension_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "corrupt.docx",
        b"PK\x03\x04corrupt archive",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "File content does not match "
        "the filename extension"
    )

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_txt_with_binary_nul_byte_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "binary.txt",
        b"hello\x00world",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "File content does not match "
        "the filename extension"
    )

    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_invalid_utf8_txt_is_rejected(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        file_storage.settings,
        "storage_path",
        str(tmp_path),
    )

    file = make_upload(
        "binary.txt",
        b"\xff\xfe\xfa\xfb",
    )

    with pytest.raises(HTTPException) as exc_info:
        await file_storage.save_uploaded_file(file)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == (
        "File content does not match "
        "the filename extension"
    )

    assert not list(tmp_path.iterdir())