from app.schemas.query import RetrievedChunk
from app.services.context import (
    ContextResult,
    ContextSource,
    build_context,
    deduplicate_chunks,
)


def test_build_context_from_single_chunk():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="finance-policy.txt",
            chunk_index=0,
            department_ids=[10],
            text="Finance policy information.",
        )
    ]

    result = build_context(chunks)

    assert isinstance(result, ContextResult)

    assert result.text == (
        "[Source: finance-policy.txt, chunk 0]\n"
        "Finance policy information."
    )

    assert result.sources == [
        ContextSource(
            document_id=1,
            filename="finance-policy.txt",
            chunk_index=0,
        )
    ]


def test_build_context_preserves_chunk_order():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="policy.txt",
            chunk_index=0,
            department_ids=[10],
            text="First chunk.",
        ),
        RetrievedChunk(
            document_id=1,
            filename="policy.txt",
            chunk_index=1,
            department_ids=[10],
            text="Second chunk.",
        ),
        RetrievedChunk(
            document_id=2,
            filename="handbook.txt",
            chunk_index=0,
            department_ids=[10],
            text="Third chunk.",
        ),
    ]

    result = build_context(chunks)

    assert result.text == (
        "[Source: policy.txt, chunk 0]\n"
        "First chunk.\n\n"
        "[Source: policy.txt, chunk 1]\n"
        "Second chunk.\n\n"
        "[Source: handbook.txt, chunk 0]\n"
        "Third chunk."
    )

    assert result.sources == [
        ContextSource(
            document_id=1,
            filename="policy.txt",
            chunk_index=0,
        ),
        ContextSource(
            document_id=1,
            filename="policy.txt",
            chunk_index=1,
        ),
        ContextSource(
            document_id=2,
            filename="handbook.txt",
            chunk_index=0,
        ),
    ]


def test_build_context_with_no_chunks():
    result = build_context([])

    assert result.text == ""
    assert result.sources == []


def test_build_context_does_not_include_department_ids():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="finance-policy.txt",
            chunk_index=0,
            department_ids=[10],
            text="Confidential finance information.",
        )
    ]

    result = build_context(chunks)

    assert "10" not in result.text
    assert "department_ids" not in result.text

    assert result.sources == [
        ContextSource(
            document_id=1,
            filename="finance-policy.txt",
            chunk_index=0,
        )
    ]


def test_deduplicate_chunks_removes_duplicate_chunk_identity():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="policy.txt",
            chunk_index=0,
            department_ids=[10],
            text="First version.",
        ),
        RetrievedChunk(
            document_id=1,
            filename="policy.txt",
            chunk_index=0,
            department_ids=[10],
            text="Duplicate version.",
        ),
        RetrievedChunk(
            document_id=1,
            filename="policy.txt",
            chunk_index=1,
            department_ids=[10],
            text="Second chunk.",
        ),
    ]

    result = deduplicate_chunks(chunks)

    assert result == [
        chunks[0],
        chunks[2],
    ]


def test_deduplicate_chunks_preserves_identical_text_from_different_documents():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="policy-a.txt",
            chunk_index=0,
            department_ids=[10],
            text="The same policy statement.",
        ),
        RetrievedChunk(
            document_id=2,
            filename="policy-b.txt",
            chunk_index=0,
            department_ids=[10],
            text="The same policy statement.",
        ),
    ]

    result = deduplicate_chunks(chunks)

    assert result == chunks