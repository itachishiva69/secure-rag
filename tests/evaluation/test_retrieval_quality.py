import pytest

from app.models import Department, Document, User
from app.models.enums import UserRole
from app.rag import qdrant_store
from app.services.retrieval import retrieve_documents


EVALUATION_DOCUMENTS = {
    "jwt-authentication.txt": [
        (
            "JWT authentication overview. JSON Web Tokens "
            "are used to represent authenticated user "
            "identity between a client and server."
        ),
        (
            "JWT tokens are digitally signed so the server "
            "can verify that the token was issued by a "
            "trusted authority."
        ),
        (
            "A JWT commonly contains claims such as the "
            "subject identifying the user and an expiration "
            "time that limits how long the token remains valid."
        ),
        (
            "Protected API endpoints validate the JWT before "
            "allowing the authenticated user to access "
            "protected resources."
        ),
        (
            "Expired or invalid JWT tokens must be rejected "
            "rather than granting access to protected "
            "resources."
        ),
    ],
    "deployment-policy.txt": [
        (
            "The deployment policy defines the process for "
            "releasing software into production environments."
        ),
        (
            "All production changes must undergo peer code "
            "review before they can be released."
        ),
        (
            "Automated tests must pass successfully before "
            "a production deployment is approved."
        ),
        (
            "Production releases require explicit deployment "
            "approval from an authorized reviewer."
        ),
        (
            "After deployment, the release must be verified "
            "to ensure the application is operating correctly."
        ),
    ],
    "finance-policy.txt": [
        (
            "The finance policy describes the organization's "
            "annual budgeting and financial planning process."
        ),
        (
            "Departments prepare annual budgets based on "
            "expected operational requirements and planned "
            "expenditure."
        ),
        (
            "Financial expenses may require approval before "
            "money can be committed or spent."
        ),
        (
            "Financial controls are used to prevent "
            "unauthorized spending and maintain accountability."
        ),
        (
            "Accounting procedures define how approved "
            "expenses are recorded and reported."
        ),
    ],
    "incident-response.txt": [
        (
            "The incident response policy defines how "
            "security incidents are handled."
        ),
        (
            "Employees should report suspected security "
            "incidents to the security team immediately."
        ),
        (
            "Incident response begins with containment to "
            "limit the impact of the security event."
        ),
        (
            "Security teams investigate incidents to determine "
            "the cause, affected systems, and scope."
        ),
        (
            "After remediation, significant incidents should "
            "undergo a post-incident review."
        ),
    ],
    "employee-onboarding.txt": [
        (
            "Employee onboarding covers the activities required "
            "when a new employee joins the organization."
        ),
        (
            "New employees receive accounts and appropriate "
            "access to systems required for their role."
        ),
        (
            "Security training introduces employees to "
            "organizational security requirements."
        ),
        (
            "Employees must acknowledge relevant company "
            "policies during the onboarding process."
        ),
        (
            "Managers and administrators verify that required "
            "onboarding activities have been completed."
        ),
    ],
}


PARAPHRASED_QUERIES = [
    (
        "What proves that an authentication token came from a trusted issuer?",
        "jwt-authentication.txt",
        1,
    ),
    (
        "How can the system tell whether a user's login credential is still valid?",
        "jwt-authentication.txt",
        2,
    ),
    (
        "What should the API do if a user's token has already expired?",
        "jwt-authentication.txt",
        4,
    ),
    (
        "Can developers release code without having another person review it first?",
        "deployment-policy.txt",
        1,
    ),
    (
        "What must be completed before a release can receive the go-ahead?",
        "deployment-policy.txt",
        2,
    ),
    (
        "What happens after new software has been pushed live?",
        "deployment-policy.txt",
        4,
    ),
    (
        "How does each department plan its spending for the coming year?",
        "finance-policy.txt",
        1,
    ),
    (
        "What safeguards stop people from spending company money without authorization?",
        "finance-policy.txt",
        3,
    ),
    (
        "Where are accepted financial transactions documented?",
        "finance-policy.txt",
        4,
    ),
    (
        "Who should an employee contact when they notice something that may be a security breach?",
        "incident-response.txt",
        1,
    ),
    (
        "What is done first to keep a security problem from spreading?",
        "incident-response.txt",
        2,
    ),
    (
        "How does the security team determine what caused an incident?",
        "incident-response.txt",
        3,
    ),
    (
        "What happens to a new worker's access to company systems?",
        "employee-onboarding.txt",
        1,
    ),
    (
        "What kind of security education is given to people when they join?",
        "employee-onboarding.txt",
        2,
    ),
    (
        "What do new hires have to formally agree to?",
        "employee-onboarding.txt",
        3,
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
        for filename in EVALUATION_DOCUMENTS
    ]

    db_session.add_all(documents)
    db_session.flush()

    for document in documents:
        document.departments = [department]

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
                chunks=EVALUATION_DOCUMENTS[
                    document.filename
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


def reciprocal_rank(
    returned_chunks,
    expected_chunk,
):
    for index, chunk in enumerate(
        returned_chunks,
        start=1,
    ):
        if chunk == expected_chunk:
            return 1.0 / index

    return 0.0


@pytest.mark.parametrize(
    "query,expected_filename,expected_chunk_index",
    PARAPHRASED_QUERIES,
)
def test_candidate_retrieval_returns_relevant_chunk(
    db_session,
    query,
    expected_filename,
    expected_chunk_index,
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
            db=db_session,
            query=query,
            current_user=user,
            limit=10,
        )

        assert results is not None

        returned_chunks = [
            (
                point.payload["filename"],
                point.payload["chunk_index"],
            )
            for point in results.points
        ]

        expected_chunk = (
            expected_filename,
            expected_chunk_index,
        )

        assert expected_chunk in returned_chunks

        print(
            f"\nQuery: {query}"
            f"\nExpected: {expected_chunk}"
            f"\nTop-10: {returned_chunks}"
        )

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )


def test_candidate_retrieval_baseline(
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
    top_5_hits = 0
    top_10_hits = 0

    reciprocal_ranks = []

    total_queries = len(
        PARAPHRASED_QUERIES
    )

    try:
        indexed_document_ids = index_evaluation_documents(
            department,
            documents,
        )

        for (
            query,
            expected_filename,
            expected_chunk_index,
        ) in PARAPHRASED_QUERIES:
            results = retrieve_documents(
                db=db_session,
                query=query,
                current_user=user,
                limit=10,
            )

            returned_chunks = [
                (
                    point.payload["filename"],
                    point.payload["chunk_index"],
                )
                for point in results.points
            ]

            expected_chunk = (
                expected_filename,
                expected_chunk_index,
            )

            if (
                returned_chunks
                and returned_chunks[0]
                == expected_chunk
            ):
                top_1_hits += 1

            if expected_chunk in returned_chunks[:3]:
                top_3_hits += 1

            if expected_chunk in returned_chunks[:5]:
                top_5_hits += 1

            if expected_chunk in returned_chunks[:10]:
                top_10_hits += 1

            reciprocal_ranks.append(
                reciprocal_rank(
                    returned_chunks,
                    expected_chunk,
                )
            )

        recall_at_1 = (
            top_1_hits / total_queries
        )

        recall_at_3 = (
            top_3_hits / total_queries
        )

        recall_at_5 = (
            top_5_hits / total_queries
        )

        recall_at_10 = (
            top_10_hits / total_queries
        )

        mean_reciprocal_rank = (
            sum(reciprocal_ranks)
            / total_queries
        )

        print(
            "\nCandidate retrieval baseline:"
            f"\n  Queries: {total_queries}"
            f"\n  Recall@1: {recall_at_1:.2%}"
            f"\n  Recall@3: {recall_at_3:.2%}"
            f"\n  Recall@5: {recall_at_5:.2%}"
            f"\n  Recall@10: {recall_at_10:.2%}"
            f"\n  MRR: {mean_reciprocal_rank:.4f}"
        )

        assert total_queries > 0
        assert recall_at_1 <= recall_at_3
        assert recall_at_3 <= recall_at_5
        assert recall_at_5 <= recall_at_10
        assert 0.0 <= mean_reciprocal_rank <= 1.0

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )


def test_candidate_retrieval_respects_department_authorization(
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
            db=db_session,
            query=(
                "How does the system verify a user's "
                "authentication token?"
            ),
            current_user=user,
            limit=10,
        )

        assert results is not None

        for point in results.points:
            payload = point.payload

            assert payload["department_ids"] == [
                department.id
            ]

    finally:
        for document_id in indexed_document_ids:
            qdrant_store.delete_document_vectors(
                document_id
            )