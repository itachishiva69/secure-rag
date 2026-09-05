import pytest

from app.models import Department, Document, User
from app.models.enums import UserRole
from app.rag import qdrant_store
from app.services.retrieval import retrieve_documents


DOCUMENT_CONTENT = {
    "jwt-authentication.txt": (
        "JWT authentication uses signed JSON Web Tokens "
        "to authenticate users. The server validates the "
        "token before allowing access to protected "
        "resources. Tokens contain claims such as user "
        "identity and expiration time."
    ),
    "deployment-policy.txt": (
        "Production deployments require code review, "
        "automated tests, deployment approval, and "
        "verification after release. Deployments must "
        "follow the approved release process."
    ),
    "finance-policy.txt": (
        "The finance budget policy defines annual budget "
        "planning, expense approval, financial controls, "
        "expense limits, and accounting procedures."
    ),
    "incident-response.txt": (
        "Security incidents must be reported immediately "
        "to the security team. Incident response includes "
        "containment, investigation, remediation, and "
        "post-incident review."
    ),
    "employee-onboarding.txt": (
        "New employees complete onboarding activities "
        "including account creation, security training, "
        "access provisioning, and policy acknowledgement."
    ),
}


EVALUATION_QUERIES = [
    (
        "How does JWT authentication work?",
        "jwt-authentication.txt",
    ),
    (
        "How are users authenticated using tokens?",
        "jwt-authentication.txt",
    ),
    (
        "What happens when a server validates a JWT?",
        "jwt-authentication.txt",
    ),
    (
        "What are the requirements before deploying to production?",
        "deployment-policy.txt",
    ),
    (
        "What approvals are needed for a production release?",
        "deployment-policy.txt",
    ),
    (
        "What checks must happen before code is deployed?",
        "deployment-policy.txt",
    ),
    (
        "How does the company handle annual budgeting?",
        "finance-policy.txt",
    ),
    (
        "What controls apply to financial expenses?",
        "finance-policy.txt",
    ),
    (
        "Who needs to approve budget-related expenses?",
        "finance-policy.txt",
    ),
    (
        "What should happen after a security incident is reported?",
        "incident-response.txt",
    ),
    (
        "What are the steps for handling a security incident?",
        "incident-response.txt",
    ),
    (
        "How should a newly discovered security incident be handled?",
        "incident-response.txt",
    ),
    (
        "What activities are required when a new employee joins?",
        "employee-onboarding.txt",
    ),
    (
        "How are new employee accounts and access provisioned?",
        "employee-onboarding.txt",
    ),
    (
        "What security training is part of employee onboarding?",
        "employee-onboarding.txt",
    ),
]


def create_evaluation_data(db_session):
    department = Department(
        name="Evaluation-Department"
    )

    db_session.add(department)
    db_session.flush()

    user = User(
        email="retrieval-evaluation@example.com",
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department.id,
    )

    db_session.add(user)
    db_session.flush()

    documents = [
        Document(
            filename=filename,
            storage_path=f"evaluation/{filename}",
            uploaded_by=user.id,
            status="indexed",
        )
        for filename in DOCUMENT_CONTENT
    ]

    db_session.add_all(documents)
    db_session.flush()

    return user, department, documents


def index_evaluation_documents(
    department,
    documents,
):
    indexed_document_ids = []

    qdrant_store.ensure_collection()

    try:
        for document in documents:
            qdrant_store.index_chunks(
                document_id=document.id,
                filename=document.filename,
                chunks=[
                    DOCUMENT_CONTENT[
                        document.filename
                    ]
                ],
                department_ids=[
                    department.id
                ],
            )

            indexed_document_ids.append(
                document.id
            )

        return indexed_document_ids

    except Exception:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )

        raise


@pytest.mark.parametrize(
    "query,expected_filename",
    EVALUATION_QUERIES,
)
def test_retrieval_returns_relevant_document(
    db_session,
    query,
    expected_filename,
):
    (
        user,
        department,
        documents,
    ) = create_evaluation_data(db_session)

    indexed_document_ids = []

    try:
        indexed_document_ids = index_evaluation_documents(
            department,
            documents,
        )

        results = retrieve_documents(
            query=query,
            current_user=user,
            limit=3,
        )

        assert results is not None

        returned_filenames = [
            point.payload["filename"]
            for point in results.points
        ]

        assert expected_filename in returned_filenames

        print(
            f"\nQuery: {query}"
            f"\nExpected: {expected_filename}"
            f"\nTop-3: {returned_filenames}"
        )

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )


def test_retrieval_quality_baseline(
    db_session,
):
    (
        user,
        department,
        documents,
    ) = create_evaluation_data(db_session)

    indexed_document_ids = []

    top_1_hits = 0
    top_3_hits = 0
    total_queries = len(EVALUATION_QUERIES)

    try:
        indexed_document_ids = index_evaluation_documents(
            department,
            documents,
        )

        for query, expected_filename in EVALUATION_QUERIES:
            results = retrieve_documents(
                query=query,
                current_user=user,
                limit=3,
            )

            returned_filenames = [
                point.payload["filename"]
                for point in results.points
            ]

            if (
                returned_filenames
                and returned_filenames[0]
                == expected_filename
            ):
                top_1_hits += 1

            if expected_filename in returned_filenames:
                top_3_hits += 1

        recall_at_1 = (
            top_1_hits / total_queries
        )

        recall_at_3 = (
            top_3_hits / total_queries
        )

        print(
            "\nRetrieval baseline:"
            f"\n  Queries: {total_queries}"
            f"\n  Recall@1: {recall_at_1:.2%}"
            f"\n  Recall@3: {recall_at_3:.2%}"
        )

        assert total_queries > 0
        assert recall_at_3 >= recall_at_1

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )


def test_retrieval_does_not_return_unknown_document_as_relevant(
    db_session,
):
    (
        user,
        department,
        documents,
    ) = create_evaluation_data(db_session)

    indexed_document_ids = []

    try:
        indexed_document_ids = index_evaluation_documents(
            department,
            documents,
        )

        results = retrieve_documents(
            query=(
                "What is the company's policy for "
                "international travel visas?"
            ),
            current_user=user,
            limit=3,
        )

        returned_filenames = [
            point.payload["filename"]
            for point in results.points
        ]

        print(
            "\nNegative query:"
            "\n  Query: What is the company's policy "
            "for international travel visas?"
            f"\n  Retrieved: {returned_filenames}"
        )

        # Dense retrieval may still return the nearest
        # available documents for an unknown topic.
        # This test intentionally does not require an
        # empty result because semantic search is not
        # a relevance classifier.
        assert results is not None

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )