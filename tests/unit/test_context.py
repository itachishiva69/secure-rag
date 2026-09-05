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

    result = build_context(
        chunks,
        max_chars=1000,
    )

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

    result = build_context(
        chunks,
        max_chars=1000,
    )

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
    result = build_context(
        [],
        max_chars=1000,
    )

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

    result = build_context(
        chunks,
        max_chars=1000,
    )

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


def test_build_context_respects_character_budget():
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
    ]

    first_part = (
        "[Source: policy.txt, chunk 0]\n"
        "First chunk."
    )

    result = build_context(
        chunks,
        max_chars=len(first_part),
    )

    assert result.text == first_part

    assert result.sources == [
        ContextSource(
            document_id=1,
            filename="policy.txt",
            chunk_index=0,
        )
    ]


def test_build_context_never_splits_a_chunk():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="policy.txt",
            chunk_index=0,
            department_ids=[10],
            text="This entire chunk must remain intact.",
        )
    ]

    result = build_context(
        chunks,
        max_chars=20,
    )

    assert result.text == ""
    assert result.sources == []


def test_build_context_preserves_rank_order_when_budget_is_reached():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="first.txt",
            chunk_index=0,
            department_ids=[10],
            text="Highest ranked result.",
        ),
        RetrievedChunk(
            document_id=2,
            filename="second.txt",
            chunk_index=0,
            department_ids=[10],
            text="Lower ranked result.",
        ),
    ]

    first_part = (
        "[Source: first.txt, chunk 0]\n"
        "Highest ranked result."
    )

    result = build_context(
        chunks,
        max_chars=len(first_part),
    )

    assert result.text == first_part

    assert result.sources == [
        ContextSource(
            document_id=1,
            filename="first.txt",
            chunk_index=0,
        )
    ]


def test_build_context_rejects_non_positive_budget():
    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="policy.txt",
            chunk_index=0,
            department_ids=[10],
            text="Policy information.",
        )
    ]

    for max_chars in [0, -1]:
        try:
            build_context(
                chunks,
                max_chars=max_chars,
            )
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert str(exc) == (
                "max_chars must be greater than zero"
            )