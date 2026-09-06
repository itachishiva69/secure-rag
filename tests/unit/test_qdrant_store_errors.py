from unittest.mock import patch

import pytest

from app.rag import qdrant_store


def test_qdrant_collection_lookup_failure_is_wrapped():
    with patch.object(
        qdrant_store.client,
        "get_collections",
        side_effect=RuntimeError(
            "simulated Qdrant connection failure"
        ),
    ):
        with pytest.raises(
            qdrant_store.QdrantStoreError
        ) as exc_info:
            qdrant_store.search(
                query="company policy",
                allowed_department_ids=[1],
                limit=5,
            )

    assert str(exc_info.value) == (
        "Qdrant collection lookup failed"
    )


def test_qdrant_search_failure_is_wrapped():
    with patch.object(
        qdrant_store,
        "ensure_collection",
    ), patch.object(
        qdrant_store,
        "get_embedding_service",
    ) as mock_embedding:
        mock_embedding.return_value.embed_query.return_value = [
            0.1,
            0.2,
            0.3,
        ]

        with patch.object(
            qdrant_store.client,
            "query_points",
            side_effect=RuntimeError(
                "simulated Qdrant search failure"
            ),
        ):
            with pytest.raises(
                qdrant_store.QdrantStoreError
            ) as exc_info:
                qdrant_store.search(
                    query="company policy",
                    allowed_department_ids=[1],
                    limit=5,
                )

    assert str(exc_info.value) == (
        "Qdrant search failed"
    )


def test_qdrant_search_rejects_malformed_response():
    with patch.object(
        qdrant_store,
        "ensure_collection",
    ), patch.object(
        qdrant_store,
        "get_embedding_service",
    ) as mock_embedding:
        mock_embedding.return_value.embed_query.return_value = [
            0.1,
            0.2,
            0.3,
        ]

        with patch.object(
            qdrant_store.client,
            "query_points",
            return_value=object(),
        ):
            with pytest.raises(
                qdrant_store.QdrantStoreError
            ) as exc_info:
                qdrant_store.search(
                    query="company policy",
                    allowed_department_ids=[1],
                    limit=5,
                )

    assert str(exc_info.value) == (
        "Qdrant search returned an invalid response"
    )


def test_empty_department_authorization_does_not_call_qdrant():
    with patch.object(
        qdrant_store,
        "ensure_collection",
    ) as mock_ensure_collection, patch.object(
        qdrant_store.client,
        "query_points",
    ) as mock_query_points, patch.object(
        qdrant_store,
        "get_embedding_service",
    ) as mock_embedding:
        result = qdrant_store.search(
            query="confidential information",
            allowed_department_ids=[],
            limit=5,
        )

    assert result == []

    mock_ensure_collection.assert_not_called()
    mock_query_points.assert_not_called()
    mock_embedding.assert_not_called()


def test_qdrant_index_failure_is_wrapped():
    with patch.object(
        qdrant_store,
        "ensure_collection",
    ), patch.object(
        qdrant_store,
        "get_embedding_service",
    ) as mock_embedding:
        mock_embedding.return_value.embed_documents.return_value = [
            [0.1, 0.2, 0.3],
        ]

        with patch.object(
            qdrant_store.client,
            "upsert",
            side_effect=RuntimeError(
                "simulated Qdrant upsert failure"
            ),
        ):
            with pytest.raises(
                qdrant_store.QdrantStoreError
            ) as exc_info:
                qdrant_store.index_chunks(
                    document_id=1,
                    filename="test.txt",
                    chunks=["Test content."],
                    department_ids=[1],
                )

    assert str(exc_info.value) == (
        "Qdrant chunk indexing failed"
    )


def test_qdrant_delete_failure_is_wrapped():
    with patch.object(
        qdrant_store,
        "_collection_exists",
        return_value=True,
    ), patch.object(
        qdrant_store.client,
        "delete",
        side_effect=RuntimeError(
            "simulated Qdrant delete failure"
        ),
    ):
        with pytest.raises(
            qdrant_store.QdrantStoreError
        ) as exc_info:
            qdrant_store.delete_document_vectors(
                document_id=123
            )

    assert str(exc_info.value) == (
        "Qdrant document vector deletion failed"
    )