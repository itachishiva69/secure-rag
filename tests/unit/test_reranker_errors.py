from unittest.mock import Mock

import pytest

from app.rag.reranker import (
    Reranker,
    RerankerError,
)
from app.schemas.query import RetrievedChunk


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

    with pytest.raises(RerankerError) as exc_info:
        Reranker(
            model_name="test-model"
        )

    assert str(exc_info.value) == (
        "Reranker model could not be loaded"
    )


def test_reranker_inference_failure_is_wrapped():
    reranker = object.__new__(Reranker)

    reranker.model = Mock()

    reranker.model.predict.side_effect = (
        RuntimeError(
            "internal inference failure"
        )
    )

    chunk = RetrievedChunk(
        document_id=1,
        filename="test.txt",
        chunk_index=0,
        department_ids=[1],
        text="Test document content.",
    )

    with pytest.raises(RerankerError) as exc_info:
        reranker.rerank(
            query="test query",
            chunks=[chunk],
            limit=1,
        )

    assert str(exc_info.value) == (
        "Reranker inference failed"
    )


def test_reranker_rejects_wrong_score_count():
    reranker = object.__new__(Reranker)

    reranker.model = Mock()
    reranker.model.predict.return_value = [
        1.0
    ]

    chunks = [
        RetrievedChunk(
            document_id=1,
            filename="test.txt",
            chunk_index=0,
            department_ids=[1],
            text="First chunk.",
        ),
        RetrievedChunk(
            document_id=1,
            filename="test.txt",
            chunk_index=1,
            department_ids=[1],
            text="Second chunk.",
        ),
    ]

    with pytest.raises(RerankerError) as exc_info:
        reranker.rerank(
            query="test query",
            chunks=chunks,
            limit=2,
        )

    assert str(exc_info.value) == (
        "Reranker returned an unexpected "
        "number of scores"
    )