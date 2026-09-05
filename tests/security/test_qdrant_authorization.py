from unittest.mock import patch

from app.rag import qdrant_store


def test_empty_department_access_returns_no_results():
    with patch.object(
        qdrant_store,
        "ensure_collection",
    ) as mock_ensure_collection, patch.object(
        qdrant_store,
        "get_embedding_service",
    ) as mock_embedding_service:

        result = qdrant_store.search(
            query="engineering authentication",
            allowed_department_ids=[],
            limit=5,
        )

        assert result == []

        mock_ensure_collection.assert_not_called()
        mock_embedding_service.assert_not_called()


def test_department_filter_is_applied():
    fake_embedding_service = mock_embedding_service = patch.object(
        qdrant_store,
        "get_embedding_service",
    )

    with fake_embedding_service as embedding_service:
        embedding_service.return_value.embed_query.return_value = [
            0.1,
            0.2,
            0.3,
        ]

        with patch.object(
            qdrant_store,
            "ensure_collection",
        ), patch.object(
            qdrant_store.client,
            "query_points",
        ) as mock_query_points:

            qdrant_store.search(
                query="engineering authentication",
                allowed_department_ids=[3],
                limit=5,
            )

            mock_query_points.assert_called_once()

            kwargs = mock_query_points.call_args.kwargs

            query_filter = kwargs["query_filter"]

            assert query_filter is not None
            assert len(query_filter.must) == 1

            condition = query_filter.must[0]

            assert condition.key == "department_ids"
            assert condition.match.any == [3]


def test_multiple_departments_are_allowed():
    with patch.object(
        qdrant_store,
        "get_embedding_service",
    ) as embedding_service:
        embedding_service.return_value.embed_query.return_value = [
            0.1,
            0.2,
            0.3,
        ]

        with patch.object(
            qdrant_store,
            "ensure_collection",
        ), patch.object(
            qdrant_store.client,
            "query_points",
        ) as mock_query_points:

            qdrant_store.search(
                query="company policy",
                allowed_department_ids=[2, 3],
                limit=10,
            )

            kwargs = mock_query_points.call_args.kwargs

            query_filter = kwargs["query_filter"]

            condition = query_filter.must[0]

            assert condition.key == "department_ids"
            assert condition.match.any == [2, 3]