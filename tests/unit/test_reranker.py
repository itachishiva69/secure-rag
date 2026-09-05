from unittest.mock import MagicMock, patch

import pytest

from app.rag.reranker import (
    Reranker,
    RerankedChunk,
)
from app.schemas.query import RetrievedChunk


def create_chunk(
    document_id: int,
    filename: str,
    chunk_index: int,
    text: str,
):
    return RetrievedChunk(
        document_id=document_id,
        filename=filename,
        chunk_index=chunk_index,
        department_ids=[1],
        text=text,
    )


@patch("app.rag.reranker.CrossEncoder")
def test_reranker_orders_chunks_by_score(
    mock_cross_encoder,
):
    mock_model = MagicMock()
    mock_cross_encoder.return_value = mock_model

    mock_model.predict.return_value = [
        0.2,
        0.9,
        0.5,
    ]

    reranker = Reranker(
        model_name="test-model"
    )

    chunks = [
        create_chunk(
            1,
            "first.txt",
            0,
            "First passage.",
        ),
        create_chunk(
            2,
            "second.txt",
            0,
            "Second passage.",
        ),
        create_chunk(
            3,
            "third.txt",
            0,
            "Third passage.",
        ),
    ]

    results = reranker.rerank(
        query="What is relevant?",
        chunks=chunks,
        limit=3,
    )

    assert [
        result.chunk.filename
        for result in results
    ] == [
        "second.txt",
        "third.txt",
        "first.txt",
    ]

    assert [
        result.score
        for result in results
    ] == [
        0.9,
        0.5,
        0.2,
    ]

    mock_model.predict.assert_called_once_with(
        [
            (
                "What is relevant?",
                "First passage.",
            ),
            (
                "What is relevant?",
                "Second passage.",
            ),
            (
                "What is relevant?",
                "Third passage.",
            ),
        ],
        show_progress_bar=False,
    )


@patch("app.rag.reranker.CrossEncoder")
def test_reranker_applies_limit(
    mock_cross_encoder,
):
    mock_model = MagicMock()
    mock_cross_encoder.return_value = mock_model

    mock_model.predict.return_value = [
        0.9,
        0.8,
        0.7,
    ]

    reranker = Reranker(
        model_name="test-model"
    )

    chunks = [
        create_chunk(
            1,
            "one.txt",
            0,
            "One.",
        ),
        create_chunk(
            2,
            "two.txt",
            0,
            "Two.",
        ),
        create_chunk(
            3,
            "three.txt",
            0,
            "Three.",
        ),
    ]

    results = reranker.rerank(
        query="Question",
        chunks=chunks,
        limit=2,
    )

    assert len(results) == 2


@patch("app.rag.reranker.CrossEncoder")
def test_reranker_returns_empty_for_empty_chunks(
    mock_cross_encoder,
):
    reranker = Reranker(
        model_name="test-model"
    )

    results = reranker.rerank(
        query="Question",
        chunks=[],
        limit=5,
    )

    assert results == []

    mock_cross_encoder.return_value.predict.assert_not_called()


@patch("app.rag.reranker.CrossEncoder")
def test_reranker_rejects_empty_query(
    mock_cross_encoder,
):
    reranker = Reranker(
        model_name="test-model"
    )

    chunks = [
        create_chunk(
            1,
            "test.txt",
            0,
            "Test.",
        )
    ]

    with pytest.raises(
        ValueError,
        match="Query cannot be empty",
    ):
        reranker.rerank(
            query="   ",
            chunks=chunks,
        )


@patch("app.rag.reranker.CrossEncoder")
def test_reranker_rejects_invalid_limit(
    mock_cross_encoder,
):
    reranker = Reranker(
        model_name="test-model"
    )

    chunks = [
        create_chunk(
            1,
            "test.txt",
            0,
            "Test.",
        )
    ]

    with pytest.raises(
        ValueError,
        match="limit must be greater than zero",
    ):
        reranker.rerank(
            query="Question",
            chunks=chunks,
            limit=0,
        )


@patch("app.rag.reranker.CrossEncoder")
def test_reranker_uses_cpu(
    mock_cross_encoder,
):
    Reranker(
        model_name="test-model"
    )

    mock_cross_encoder.assert_called_once_with(
        "test-model",
        device="cpu",
    )