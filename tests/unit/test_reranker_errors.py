from unittest.mock import Mock

import pytest

from app.rag.reranker import (
    Reranker,
    RerankerError,
)
from app.schemas.query import RetrievedChunk


def create_chunk(
    document_id: int,
    chunk_index: int,
    text: str,
):
    return RetrievedChunk(
        document_id=document_id,
        filename=f"document-{document_id}.txt",
        chunk_index=chunk_index,
        department_ids=[1],
        text=text,
    )


def test_reranker_model_load_failure_is_wrapped(
    monkeypatch,
):
    def failing_cross_encoder(
        model_name,
        device,
    ):
        raise RuntimeError(
            "internal model loading failure"
        )

    monkeypatch.setattr(
        "app.rag.reranker.CrossEncoder",
        failing_cross_encoder,
    )

    with pytest.raises(
        RerankerError,
        match="Reranker model could not be loaded",
    ):
        Reranker(
            model_name="test-model"
        )


def test_reranker_inference_failure_is_wrapped():
    reranker = object.__new__(Reranker)

    reranker.model = Mock()

    reranker.model.predict.side_effect = (
        RuntimeError(
            "internal inference failure"
        )
    )

    chunk = create_chunk(
        document_id=1,
        chunk_index=0,
        text="Test document content.",
    )

    with pytest.raises(
        RerankerError,
        match="Reranker inference failed",
    ):
        reranker.rerank(
            query="test query",
            chunks=[chunk],
            limit=1,
        )


def test_reranker_rejects_wrong_score_count():
    reranker = object.__new__(Reranker)

    reranker.model = Mock()

    reranker.model.predict.return_value = [
        1.0,
    ]

    chunks = [
        create_chunk(
            document_id=1,
            chunk_index=0,
            text="First chunk.",
        ),
        create_chunk(
            document_id=1,
            chunk_index=1,
            text="Second chunk.",
        ),
    ]

    with pytest.raises(
        RerankerError,
        match=(
            "Reranker returned an unexpected "
            "number of scores"
        ),
    ):
        reranker.rerank(
            query="test query",
            chunks=chunks,
            limit=2,
        )


def test_reranker_rejects_malformed_scores():
    reranker = object.__new__(Reranker)

    reranker.model = Mock()

    reranker.model.predict.return_value = [
        "not-a-number",
    ]

    chunk = create_chunk(
        document_id=1,
        chunk_index=0,
        text="Test document content.",
    )

    with pytest.raises(
        RerankerError,
        match="Reranker returned invalid scores",
    ):
        reranker.rerank(
            query="test query",
            chunks=[chunk],
            limit=1,
        )


@pytest.mark.parametrize(
    "score",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def test_reranker_rejects_non_finite_scores(
    score,
):
    reranker = object.__new__(Reranker)

    reranker.model = Mock()

    reranker.model.predict.return_value = [
        score,
    ]

    chunk = create_chunk(
        document_id=1,
        chunk_index=0,
        text="Test document content.",
    )

    with pytest.raises(
        RerankerError,
        match="Reranker returned invalid scores",
    ):
        reranker.rerank(
            query="test query",
            chunks=[chunk],
            limit=1,
        )


def test_reranker_rejects_invalid_score_collection():
    reranker = object.__new__(Reranker)

    reranker.model = Mock()

    reranker.model.predict.return_value = (
        1.0
    )

    chunk = create_chunk(
        document_id=1,
        chunk_index=0,
        text="Test document content.",
    )

    with pytest.raises(
        RerankerError,
        match="Reranker returned invalid scores",
    ):
        reranker.rerank(
            query="test query",
            chunks=[chunk],
            limit=1,
        )