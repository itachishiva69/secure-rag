from codecs import getincrementaldecoder
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, is_zipfile

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


settings = get_settings()

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".docx",
}

READ_CHUNK_SIZE = 1024 * 1024

DOCX_REQUIRED_MEMBERS = {
    "[Content_Types].xml",
    "word/document.xml",
}


def _is_valid_pdf(path: Path) -> bool:
    with path.open("rb") as file:
        return file.read(5) == b"%PDF-"


def _is_valid_docx(path: Path) -> bool:
    if not is_zipfile(path):
        return False

    try:
        with ZipFile(path) as archive:
            names = set(archive.namelist())

            if not DOCX_REQUIRED_MEMBERS.issubset(names):
                return False

            content_types = archive.read(
                "[Content_Types].xml"
            )
            document_xml = archive.read(
                "word/document.xml"
            )

            if not content_types or not document_xml:
                return False

    except (
        BadZipFile,
        KeyError,
        OSError,
    ):
        return False

    return True


def _is_valid_txt(path: Path) -> bool:
    decoder = getincrementaldecoder("utf-8")("strict")

    try:
        with path.open("rb") as file:
            while chunk := file.read(READ_CHUNK_SIZE):
                if b"\x00" in chunk:
                    return False

                decoder.decode(
                    chunk,
                    final=False,
                )

            decoder.decode(
                b"",
                final=True,
            )

    except (
        UnicodeDecodeError,
        OSError,
    ):
        return False

    return True


def _validate_content_signature(
    path: Path,
    extension: str,
) -> bool:
    if extension == ".pdf":
        return _is_valid_pdf(path)

    if extension == ".docx":
        return _is_valid_docx(path)

    if extension == ".txt":
        return _is_valid_txt(path)

    return False


async def save_uploaded_file(
    file: UploadFile,
) -> str:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    original_filename = Path(
        file.filename
    ).name.strip()

    if not original_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    extension = Path(
        original_filename
    ).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file type. "
                "Allowed: PDF, TXT, DOCX"
            ),
        )

    storage_dir = Path(
        settings.storage_path
    )

    storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_filename = (
        f"{uuid4().hex}{extension}"
    )

    destination = (
        storage_dir / stored_filename
    )

    max_size = (
        settings.max_upload_size_mb
        * 1024
        * 1024
    )

    total_size = 0

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(
                READ_CHUNK_SIZE
            ):
                total_size += len(chunk)

                if total_size > max_size:
                    destination.unlink(
                        missing_ok=True
                    )

                    raise HTTPException(
                        status_code=(
                            status.HTTP_413_CONTENT_TOO_LARGE
                        ),
                        detail=(
                            f"File exceeds the "
                            f"{settings.max_upload_size_mb} MB "
                            f"limit"
                        ),
                    )

                output.write(chunk)

        if total_size == 0:
            destination.unlink(
                missing_ok=True
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        if not _validate_content_signature(
            destination,
            extension,
        ):
            destination.unlink(
                missing_ok=True
            )

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "File content does not match "
                    "the filename extension"
                ),
            )

    except HTTPException:
        raise

    except Exception:
        destination.unlink(
            missing_ok=True
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store file",
        )

    finally:
        await file.close()

    return str(destination)