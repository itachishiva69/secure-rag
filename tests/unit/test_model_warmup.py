from unittest.mock import Mock

import pytest

from app.rag.reranker import RerankerError
from app.services import model_warmup


def test_warm_models_loads_embedding_and_reranker(
    monkeypatch,
):
    embedding_service = Mock()
    embedding_service.dimension = 384
    reranker = Mock()

    monkeypatch.setattr(
        model_warmup,
        "get_embedding_service",
        lambda: embedding_service,
    )
    monkeypatch.setattr(
        model_warmup,
        "get_reranker",
        lambda: reranker,
    )

    model_warmup.warm_models.cache_clear()

    assert model_warmup.warm_models() is True


def test_warm_models_propagates_embedding_failure(
    monkeypatch,
):
    monkeypatch.setattr(
        model_warmup,
        "get_embedding_service",
        lambda: (
            (_ for _ in ()).throw(
                RuntimeError("embedding failure")
            )
        ),
    )

    model_warmup.warm_models.cache_clear()

    with pytest.raises(
        RuntimeError,
        match="embedding failure",
    ):
        model_warmup.warm_models()


def test_warm_models_allows_optional_reranker_failure(
    monkeypatch,
):
    embedding_service = Mock()
    embedding_service.dimension = 384

    monkeypatch.setattr(
        model_warmup,
        "get_embedding_service",
        lambda: embedding_service,
    )

    monkeypatch.setattr(
        model_warmup,
        "get_reranker",
        lambda: (
            (_ for _ in ()).throw(
                RerankerError("reranker failure")
            )
        ),
    )

    model_warmup.warm_models.cache_clear()

    assert model_warmup.warm_models() is True
