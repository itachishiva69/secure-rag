from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


settings = get_settings()

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".docx",
}


async def save_uploaded_file(file: UploadFile) -> str:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    original_filename = Path(file.filename).name
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unsupported file type. "
                "Allowed: PDF, TXT, DOCX"
            ),
        )

    storage_dir = Path(settings.storage_path)
    storage_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    stored_filename = f"{uuid4().hex}{extension}"
    destination = storage_dir / stored_filename

    max_size = settings.max_upload_size_mb * 1024 * 1024
    total_size = 0

    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)

                if total_size > max_size:
                    destination.unlink(missing_ok=True)

                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=(
                            f"File exceeds the "
                            f"{settings.max_upload_size_mb} MB limit"
                        ),
                    )

                output.write(chunk)

    except HTTPException:
        raise

    except Exception:
        destination.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store uploaded file",
        )

    finally:
        await file.close()

    return str(destination)