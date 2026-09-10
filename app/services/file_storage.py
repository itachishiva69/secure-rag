from codecs import getincrementaldecoder
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, is_zipfile

import cloudinary
import cloudinary.uploader
import cloudinary.utils
import requests
from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)

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

CLOUDINARY_PREFIX = "cloudinary://"


def _configure_cloudinary() -> None:
    if not (
        settings.cloudinary_cloud_name
        and settings.cloudinary_api_key
        and settings.cloudinary_api_secret
    ):
        raise RuntimeError(
            "Cloudinary configuration is incomplete"
        )

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )


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


def _save_local_file(
    file: UploadFile,
    extension: str,
) -> str:
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
            while chunk := file.file.read(
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

    except Exception as exc:
        destination.unlink(
            missing_ok=True
        )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store file",
        ) from exc

    logger.info(
        "stored_file_verified",
        extra={
            "backend": "local",
            "path": str(destination),
            "exists": destination.exists(),
            "size": (
                destination.stat().st_size
                if destination.exists()
                else None
            ),
        },
    )

    return str(destination)


def _save_cloudinary_file(
    file: UploadFile,
    extension: str,
) -> str:
    _configure_cloudinary()

    total_size = 0
    max_size = (
        settings.max_upload_size_mb
        * 1024
        * 1024
    )

    with NamedTemporaryFile(
        suffix=extension,
        delete=True,
    ) as temporary_file:
        try:
            while chunk := file.file.read(
                READ_CHUNK_SIZE
            ):
                total_size += len(chunk)

                if total_size > max_size:
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

                temporary_file.write(chunk)

            if total_size == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Uploaded file is empty",
                )

            temporary_file.flush()
            temporary_file.seek(0)

            if not _validate_content_signature(
                Path(temporary_file.name),
                extension,
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "File content does not match "
                        "the filename extension"
                    ),
                )

            public_id = (
                f"documents/{uuid4().hex}{extension}"
            )

            result = cloudinary.uploader.upload(
                temporary_file.name,
                resource_type="raw",
                type="authenticated",
                public_id=public_id,
                overwrite=False,
            )

        except HTTPException:
            raise

        except Exception as exc:
            logger.exception(
                "cloudinary_upload_failed"
            )

            raise HTTPException(
                status_code=(
                    status.HTTP_502_BAD_GATEWAY
                ),
                detail="Failed to store file",
            ) from exc

    stored_reference = (
        f"{CLOUDINARY_PREFIX}"
        f"{public_id}"
    )

    logger.info(
        "stored_file_verified",
        extra={
            "backend": "cloudinary",
            "reference": stored_reference,
            "size": total_size,
            "asset_id": result.get("asset_id"),
        },
    )

    return stored_reference


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

    try:
        if settings.storage_backend == "cloudinary":
            storage_path = _save_cloudinary_file(
                file,
                extension,
            )
        else:
            storage_path = _save_local_file(
                file,
                extension,
            )

        return storage_path

    finally:
        await file.close()


def is_cloudinary_reference(
    storage_reference: str,
) -> bool:
    return storage_reference.startswith(
        CLOUDINARY_PREFIX
    )


def _cloudinary_public_id(
    storage_reference: str,
) -> str:
    if not is_cloudinary_reference(
        storage_reference
    ):
        raise ValueError(
            "Storage reference is not a Cloudinary reference"
        )

    public_id = storage_reference[
        len(CLOUDINARY_PREFIX):
    ]

    if not public_id:
        raise ValueError(
            "Cloudinary storage reference is empty"
        )

    return public_id


def materialize_stored_file(
    storage_reference: str,
) -> tuple[Path, bool]:
    """
    Return a local Path suitable for document extraction.

    Returns:
        (path, should_delete_after_use)
    """
    if not is_cloudinary_reference(
        storage_reference
    ):
        path = Path(storage_reference)

        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Stored document file not found",
            )

        return path, False

    _configure_cloudinary()

    public_id = _cloudinary_public_id(
        storage_reference
    )

    extension = Path(public_id).suffix

    try:
        signed_url = (
            cloudinary.utils.private_download_url(
                public_id=public_id,
                format=extension.lstrip("."),
                resource_type="raw",
                type="authenticated",
            )
        )

        response = requests.get(
            signed_url,
            timeout=30,
        )

        response.raise_for_status()

    except Exception as exc:
        logger.exception(
            "cloudinary_download_failed",
            extra={
                "public_id": public_id,
            },
        )

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve stored document",
        ) from exc

    temporary_file = NamedTemporaryFile(
        suffix=extension,
        delete=False,
    )

    try:
        temporary_file.write(
            response.content
        )
        temporary_file.close()

    except Exception:
        Path(
            temporary_file.name
        ).unlink(
            missing_ok=True
        )
        raise

    path = Path(
        temporary_file.name
    )

    logger.info(
        "stored_file_materialized",
        extra={
            "backend": "cloudinary",
            "public_id": public_id,
            "path": str(path),
            "size": path.stat().st_size,
        },
    )

    return path, True


def delete_stored_file(
    storage_reference: str,
) -> None:
    if is_cloudinary_reference(
        storage_reference
    ):
        _configure_cloudinary()

        public_id = _cloudinary_public_id(
            storage_reference
        )

        try:
            cloudinary.uploader.destroy(
                public_id,
                resource_type="raw",
                type="authenticated",
                invalidate=True,
            )

        except Exception as exc:
            logger.exception(
                "cloudinary_delete_failed",
                extra={
                    "public_id": public_id,
                },
            )
            raise

        return

    Path(
        storage_reference
    ).unlink(
        missing_ok=True
    )
