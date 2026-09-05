from dataclasses import dataclass

from app.core.config import get_settings
from app.schemas.query import RetrievedChunk


@dataclass(frozen=True)
class ContextSource:
    document_id: int
    filename: str
    chunk_index: int


@dataclass(frozen=True)
class ContextResult:
    text: str
    sources: list[ContextSource]


def deduplicate_chunks(
    chunks: list[RetrievedChunk],
) -> list[RetrievedChunk]:
    """
    Remove duplicate references to the same document chunk.

    Chunk identity is based on:
        document_id + chunk_index

    Original retrieval order is preserved.
    """

    seen: set[tuple[int, int]] = set()
    unique_chunks: list[RetrievedChunk] = []

    for chunk in chunks:
        chunk_key = (
            chunk.document_id,
            chunk.chunk_index,
        )

        if chunk_key in seen:
            continue

        seen.add(chunk_key)
        unique_chunks.append(chunk)

    return unique_chunks


def build_context(
    chunks: list[RetrievedChunk],
    max_chars: int | None = None,
) -> ContextResult:
    """
    Build the context that will eventually be supplied
    to the LLM.

    Authorization must already have happened before this
    function is called. This function does not make
    authorization decisions.

    Duplicate references to the same document chunk are
    removed while preserving retrieval order.

    Complete chunks are included until max_chars is reached.
    A chunk is never split or truncated.
    """

    if max_chars is None:
        max_chars = get_settings().context_max_chars

    if max_chars <= 0:
        raise ValueError(
            "max_chars must be greater than zero"
        )

    unique_chunks = deduplicate_chunks(chunks)

    if not unique_chunks:
        return ContextResult(
            text="",
            sources=[],
        )

    context_parts: list[str] = []
    sources: list[ContextSource] = []
    current_chars = 0

    for chunk in unique_chunks:
        context_part = (
            f"[Source: {chunk.filename}, "
            f"chunk {chunk.chunk_index}]\n"
            f"{chunk.text}"
        )

        separator_chars = 2 if context_parts else 0
        required_chars = (
            separator_chars + len(context_part)
        )

        if current_chars + required_chars > max_chars:
            break

        context_parts.append(context_part)

        sources.append(
            ContextSource(
                document_id=chunk.document_id,
                filename=chunk.filename,
                chunk_index=chunk.chunk_index,
            )
        )

        current_chars += required_chars

    return ContextResult(
        text="\n\n".join(context_parts),
        sources=sources,
    )