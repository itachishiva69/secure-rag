from pathlib import Path
import re

from docx import Document as DocxDocument
from pypdf import PdfReader

from fastapi import HTTPException, status


def extract_text(file_path: str) -> str:
    path = Path(file_path)

    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored document file not found",
        )

    extension = path.suffix.lower()

    if extension == ".txt":
        return _extract_txt(path)

    if extension == ".pdf":
        return _extract_pdf(path)

    if extension == ".docx":
        return _extract_docx(path)

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported file type: {extension}",
    )


def _extract_txt(path: Path) -> str:
    return path.read_text(
        encoding="utf-8",
        errors="replace",
    )


def _extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))

    pages = []

    for page in reader.pages:
        text = page.extract_text()

        if text:
            pages.append(text)

    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    document = DocxDocument(str(path))

    paragraphs = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    return "\n\n".join(paragraphs)


def normalize_text(text: str) -> str:
    text = text.replace("\x00", "")

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()