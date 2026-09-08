from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.main import app
from app.models import (
    Conversation,
    ConversationMessage,
    ConversationMessageRole,
    Department,
    User,
)
from app.models.enums import UserRole


def create_department(
    db_session,
) -> Department:
    department = Department(
        name="Conversational-Query-Department"
    )
    db_session.add(department)
    db_session.flush()
    return department


def create_user(
    db_session,
    *,
    email: str,
    department_id: int,
) -> User:
    user = User(
        email=email,
        password_hash="test-hash",
        role=UserRole.USER,
        department_id=department_id,
    )
    db_session.add(user)
    db_session.flush()
    return user


def configure_app(
    db_session,
    user: User,
) -> None:
    app.dependency_overrides[get_db] = (
        lambda: db_session
    )
    app.dependency_overrides[get_current_user] = (
        lambda: user
    )


def clear_app() -> None:
    app.dependency_overrides.clear()


def test_query_without_conversation_preserves_single_turn_behavior(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="single-turn@example.com",
        department_id=department.id,
    )
    db_session.commit()

    def fake_retrieve_documents(
        *,
        db,
        query,
        current_user,
        limit,
        reranker,
    ):
        assert db is db_session
        assert query == "What is the release process?"
        assert current_user.id == user.id
        assert limit == 5

        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "document_id": 1,
                        "filename": "release.txt",
                        "chunk_index": 0,
                        "department_ids": [department.id],
                        "text": (
                            "The release process has "
                            "four checks."
                        ),
                    }
                )
            ]
        )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            assert query == (
                "What is the release process?"
            )
            assert "four checks" in context.text
            return "There are four release checks."

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            raise AssertionError(
                "Conversational generation should not be used"
            )

    fake_provider = FakeProvider()

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_documents,
    )
    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: fake_provider,
    )

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "What is the release process?",
                "limit": 5,
            },
        )

        assert response.status_code == 200
        assert response.json()["conversation_id"] is None

        assert (
            db_session.query(
                ConversationMessage
            ).count()
            == 0
        )

    finally:
        clear_app()


def test_conversation_query_persists_user_and_assistant_messages(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="conversation-query@example.com",
        department_id=department.id,
    )

    conversation = Conversation(
        user_id=user.id,
        title="Release discussion",
    )
    db_session.add(conversation)
    db_session.commit()

    captured = {}

    def fake_retrieve_documents(
        *,
        db,
        query,
        current_user,
        limit,
        reranker,
    ):
        captured["query"] = query
        captured["current_user"] = current_user
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "document_id": 1,
                        "filename": "release.txt",
                        "chunk_index": 0,
                        "department_ids": [department.id],
                        "text": (
                            "Deployments require "
                            "four checks."
                        ),
                    }
                )
            ]
        )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError(
                "Conversational generation should be used"
            )

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            captured["previous_user_messages"] = (
                list(previous_user_messages)
            )
            assert query == (
                "What are the deployment checks?"
            )
            assert "four checks" in context.text
            return "Deployments require four checks."

    fake_provider = FakeProvider()

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_documents,
    )
    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: fake_provider,
    )

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "What are the deployment checks?",
                "limit": 5,
                "conversation_id": conversation.id,
            },
        )

        assert response.status_code == 200
        assert response.json()["conversation_id"] == (
            conversation.id
        )
        assert captured["query"] == (
            "What are the deployment checks?"
        )
        assert captured["previous_user_messages"] == []

        messages = (
            db_session.query(
                ConversationMessage
            )
            .filter(
                ConversationMessage.conversation_id
                == conversation.id
            )
            .order_by(
                ConversationMessage.id
            )
            .all()
        )

        assert [message.role for message in messages] == [
            ConversationMessageRole.USER,
            ConversationMessageRole.ASSISTANT,
        ]
        assert messages[0].content == (
            "What are the deployment checks?"
        )
        assert messages[1].content == (
            "Deployments require four checks."
        )

    finally:
        clear_app()


def test_conversation_query_loads_only_previous_user_messages(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="conversation-history@example.com",
        department_id=department.id,
    )

    conversation = Conversation(
        user_id=user.id,
        title="History",
    )
    db_session.add(conversation)
    db_session.flush()

    history = [
        (
            ConversationMessageRole.USER,
            "What is our release process?",
        ),
        (
            ConversationMessageRole.ASSISTANT,
            "The release process has four checks.",
        ),
        (
            ConversationMessageRole.USER,
            "Which check happens before deployment?",
        ),
        (
            ConversationMessageRole.ASSISTANT,
            "The validation check.",
        ),
    ]

    for role, content in history:
        db_session.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role=role,
                content=content,
            )
        )

    db_session.commit()

    captured = {}

    def fake_retrieve_documents(
        *,
        db,
        query,
        current_user,
        limit,
        reranker,
    ):
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "document_id": 1,
                        "filename": "release.txt",
                        "chunk_index": 0,
                        "department_ids": [department.id],
                        "text": "Validation happens before deployment.",
                    }
                )
            ]
        )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError(
                "Conversational generation should be used"
            )

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            captured["history"] = list(
                previous_user_messages
            )
            return "Validation happens before deployment."

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_documents,
    )
    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: FakeProvider(),
    )

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "Tell me again.",
                "conversation_id": conversation.id,
            },
        )

        assert response.status_code == 200
        assert captured["history"] == [
            "What is our release process?",
            "Which check happens before deployment?",
        ]

    finally:
        clear_app()


def test_user_cannot_query_another_users_conversation(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    owner = create_user(
        db_session,
        email="conversation-owner-query@example.com",
        department_id=department.id,
    )
    attacker = create_user(
        db_session,
        email="conversation-attacker-query@example.com",
        department_id=department.id,
    )

    conversation = Conversation(
        user_id=owner.id,
        title="Private",
    )
    db_session.add(conversation)
    db_session.commit()

    retrieve_called = False

    def fake_retrieve_documents(**kwargs):
        nonlocal retrieve_called
        retrieve_called = True
        raise AssertionError(
            "Retrieval must not run for an unauthorized conversation"
        )

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_documents,
    )

    configure_app(
        db_session,
        attacker,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "What was discussed?",
                "conversation_id": conversation.id,
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "Conversation not found"
        )
        assert retrieve_called is False

    finally:
        clear_app()


def test_conversation_query_does_not_persist_messages_when_llm_fails(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="conversation-failure@example.com",
        department_id=department.id,
    )

    conversation = Conversation(
        user_id=user.id,
        title="Failure",
    )
    db_session.add(conversation)
    db_session.commit()

    def fake_retrieve_documents(
        *,
        db,
        query,
        current_user,
        limit,
        reranker,
    ):
        return SimpleNamespace(
            points=[
                SimpleNamespace(
                    payload={
                        "document_id": 1,
                        "filename": "release.txt",
                        "chunk_index": 0,
                        "department_ids": [department.id],
                        "text": "Authorized release information.",
                    }
                )
            ]
        )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            return "unused"

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            from app.services.llm_provider import (
                LLMProviderError,
            )

            raise LLMProviderError(
                "simulated provider failure"
            )

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_documents,
    )
    monkeypatch.setattr(
        "app.api.query.get_llm_provider",
        lambda: FakeProvider(),
    )

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/",
            json={
                "query": "Tell me the release information.",
                "conversation_id": conversation.id,
            },
        )

        assert response.status_code == 502
        assert (
            db_session.query(
                ConversationMessage
            )
            .filter(
                ConversationMessage.conversation_id
                == conversation.id
            )
            .count()
            == 0
        )

    finally:
        clear_app()
