import pytest

from app.rag.reranker import Reranker
from app.services.retrieval import retrieve_documents

from tests.evaluation.test_retrieval_quality import (
    PARAPHRASED_QUERIES,
    create_evaluation_data,
    index_evaluation_documents,
)


@pytest.fixture(scope="module")
def reranker():
    return Reranker(
        model_name="cross-encoder/ms-marco-MiniLM-L6-v2"
    )


def resolve_expected_document_id(
    expected,
    documents,
) -> int:
    if isinstance(expected, int):
        return expected

    if isinstance(expected, str):
        for document in documents:
            if document.filename == expected:
                return document.id

        raise AssertionError(
            f"Could not find evaluation document "
            f"with filename: {expected}"
        )

    if hasattr(expected, "id"):
        return expected.id

    raise TypeError(
        "Unsupported expected-document value: "
        f"{type(expected).__name__}"
    )


def calculate_reciprocal_rank(
    retrieved_document_ids: list[int],
    expected_document_id: int,
) -> float:
    for rank, document_id in enumerate(
        retrieved_document_ids,
        start=1,
    ):
        if document_id == expected_document_id:
            return 1.0 / rank

    return 0.0


def test_reranker_multichunk_quality(
    db_session,
    reranker,
):
    user, department, documents = create_evaluation_data(
        db_session
    )

    index_evaluation_documents(
        department,
        documents,
    )

    recall_at_1 = 0
    recall_at_3 = 0
    recall_at_5 = 0

    reciprocal_ranks = []

    total_queries = len(PARAPHRASED_QUERIES)

    for query, expected_filename, expected_chunk_index in (
        PARAPHRASED_QUERIES
    ):
        expected_document_id = (
            resolve_expected_document_id(
                expected_filename,
                documents,
            )
        )

        results = retrieve_documents(
            db=db_session,
            query=query,
            current_user=user,
            limit=5,
            reranker=reranker,
        )

        retrieved_document_ids = [
            point.payload["document_id"]
            for point in results.points
            if point.payload
            and "document_id" in point.payload
        ]

        if expected_document_id in retrieved_document_ids[:1]:
            recall_at_1 += 1

        if expected_document_id in retrieved_document_ids[:3]:
            recall_at_3 += 1

        if expected_document_id in retrieved_document_ids[:5]:
            recall_at_5 += 1

        reciprocal_ranks.append(
            calculate_reciprocal_rank(
                retrieved_document_ids,
                expected_document_id,
            )
        )

    recall_at_1_score = (
        recall_at_1 / total_queries
    )

    recall_at_3_score = (
        recall_at_3 / total_queries
    )

    recall_at_5_score = (
        recall_at_5 / total_queries
    )

    mrr = (
        sum(reciprocal_ranks)
        / total_queries
    )

    print(
        "\nReranker multi-chunk quality:"
    )
    print(
        f"Recall@1:  {recall_at_1_score:.4f}"
    )
    print(
        f"Recall@3:  {recall_at_3_score:.4f}"
    )
    print(
        f"Recall@5:  {recall_at_5_score:.4f}"
    )
    print(
        f"MRR:       {mrr:.4f}"
    )

    assert recall_at_1_score >= 0.80
    assert recall_at_3_score >= 0.80
    assert recall_at_5_score >= 0.80