from app.core.config import Settings


def test_reranker_settings_have_expected_defaults():
    settings = Settings(
        database_url="postgresql://test",
        qdrant_url="http://localhost:6333",
        jwt_secret="test-secret",
    )

    assert settings.reranker_model == (
        "cross-encoder/ms-marco-MiniLM-L6-v2"
    )

    assert settings.reranker_candidate_limit == 10


def test_reranker_settings_can_be_overridden():
    settings = Settings(
        database_url="postgresql://test",
        qdrant_url="http://localhost:6333",
        jwt_secret="test-secret",
        reranker_model="custom-reranker",
        reranker_candidate_limit=20,
    )

    assert settings.reranker_model == (
        "custom-reranker"
    )

    assert settings.reranker_candidate_limit == 20