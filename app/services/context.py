from dataclasses import dataclass

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


def build_context(
    chunks: list[RetrievedChunk],
) -> ContextResult:
    """
    Build the context that will eventually be supplied
    to the LLM.

    Authorization must already have happened before this
    function is called. This function does not make
    authorization decisions.
    """

    if not chunks:
        return ContextResult(
            text="",
            sources=[],
        )

    context_parts = []
    sources = []

    for chunk in chunks:
        context_parts.append(
            (
                f"[Source: {chunk.filename}, "
                f"chunk {chunk.chunk_index}]\n"
                f"{chunk.text}"
            )
        )

        sources.append(
            ContextSource(
                document_id=chunk.document_id,
                filename=chunk.filename,
                chunk_index=chunk.chunk_index,
            )
        )

    return ContextResult(
        text="\n\n".join(context_parts),
        sources=sources,
    )