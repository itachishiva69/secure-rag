from types import SimpleNamespace

import json

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
from app.services.llm_provider import LLMProviderError


def create_department(db_session) -> Department:
    department = Department(
        name="Streaming-Query-Department"
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


def fake_retrieve_factory(
    department_id: int,
):
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
                        "filename": "streaming.txt",
                        "chunk_index": 0,
                        "department_ids": [
                            department_id
                        ],
                        "text": (
                            "The release process "
                            "has four checks."
                        ),
                    }
                )
            ]
        )

    return fake_retrieve_documents


def parse_events(text: str) -> list[tuple[str, dict]]:
    events = []

    for raw_event in text.split("\n\n"):
        raw_event = raw_event.strip()
        if not raw_event:
            continue

        event_name = "message"
        data_lines = []

        for line in raw_event.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())

        if data_lines:
            events.append(
                (event_name, json.loads("\n".join(data_lines)))
            )

    return events


def test_streaming_query_emits_tokens_and_done(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="streaming-basic@example.com",
        department_id=department.id,
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_factory(
            department.id
        ),
    )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError(
                "Non-streaming generation should not run"
            )

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            raise AssertionError(
                "Non-streaming conversational generation should not run"
            )

        def stream(
            self,
            *,
            query,
            context,
        ):
            yield "There are "
            yield "four checks."

        def stream_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            raise AssertionError(
                "Conversational streaming should not run"
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
            "/query/stream",
            json={
                "query": "What is the release process?",
                "limit": 5,
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith(
            "text/event-stream"
        )

        events = parse_events(
            response.text
        )
        names = [name for name, _ in events]

        assert names == [
            "start",
            "token",
            "token",
            "done",
        ]

        assert [
            data["text"]
            for name, data in events
            if name == "token"
        ] == [
            "There are ",
            "four checks.",
        ]

        done = next(
            data
            for name, data in events
            if name == "done"
        )

        assert done["answer"] == (
            "There are four checks."
        )
        assert done["conversation_id"] is None

    finally:
        clear_app()


def test_conversational_streaming_persists_only_after_completion(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="streaming-conversation@example.com",
        department_id=department.id,
    )
    conversation = Conversation(
        user_id=user.id,
        title="Streaming conversation",
    )
    db_session.add(conversation)
    db_session.commit()

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_factory(
            department.id
        ),
    )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError(
                "Non-streaming generation should not run"
            )

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            raise AssertionError(
                "Non-streaming conversational generation should not run"
            )

        def stream(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError(
                "Non-conversational streaming should not run"
            )

        def stream_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            assert previous_user_messages == [
                "What was the old release process?"
            ]

            yield "The "
            yield "new process has four checks."

    db_session.add(
        ConversationMessage(
            conversation_id=conversation.id,
            role=ConversationMessageRole.USER,
            content="What was the old release process?",
        )
    )
    db_session.commit()

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
            "/query/stream",
            json={
                "query": "What is the new release process?",
                "limit": 5,
                "conversation_id": conversation.id,
            },
        )

        assert response.status_code == 200

        events = parse_events(
            response.text
        )

        done = next(
            data
            for name, data in events
            if name == "done"
        )

        assert done["conversation_id"] == (
            conversation.id
        )

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

        assert [
            message.role
            for message in messages
        ] == [
            ConversationMessageRole.USER,
            ConversationMessageRole.USER,
            ConversationMessageRole.ASSISTANT,
        ]

        assert messages[1].content == (
            "What is the new release process?"
        )
        assert messages[2].content == (
            "The new process has four checks."
        )

    finally:
        clear_app()


def test_streaming_provider_failure_does_not_persist_conversation_turn(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="streaming-failure@example.com",
        department_id=department.id,
    )
    conversation = Conversation(
        user_id=user.id,
        title="Streaming failure",
    )
    db_session.add(conversation)
    db_session.commit()

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_factory(
            department.id
        ),
    )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            raise AssertionError

        def stream(
            self,
            *,
            query,
            context,
        ):
            yield "partial"
            raise LLMProviderError(
                "simulated streaming failure"
            )

        def stream_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            yield "partial"
            raise LLMProviderError(
                "simulated streaming failure"
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
            "/query/stream",
            json={
                "query": "What is the release process?",
                "conversation_id": conversation.id,
            },
        )

        assert response.status_code == 200

        events = parse_events(
            response.text
        )
        names = [
            name
            for name, _ in events
        ]

        assert names == [
            "start",
            "token",
            "error",
        ]

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


def test_user_cannot_stream_into_another_users_conversation(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    owner = create_user(
        db_session,
        email="stream-owner@example.com",
        department_id=department.id,
    )
    attacker = create_user(
        db_session,
        email="stream-attacker@example.com",
        department_id=department.id,
    )
    conversation = Conversation(
        user_id=owner.id,
        title="Private streaming conversation",
    )
    db_session.add(conversation)
    db_session.commit()

    retrieval_called = False

    def forbidden_retrieval(**kwargs):
        nonlocal retrieval_called
        retrieval_called = True
        raise AssertionError(
            "Retrieval must not run"
        )

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        forbidden_retrieval,
    )

    configure_app(
        db_session,
        attacker,
    )

    client = TestClient(app)

    try:
        response = client.post(
            "/query/stream",
            json={
                "query": "What was discussed?",
                "conversation_id": conversation.id,
            },
        )

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "Conversation not found"
        )
        assert retrieval_called is False

    finally:
        clear_app()


def test_streaming_without_conversation_does_not_create_messages(
    db_session,
    monkeypatch,
):
    department = create_department(
        db_session
    )
    user = create_user(
        db_session,
        email="streaming-stateless@example.com",
        department_id=department.id,
    )
    db_session.commit()

    monkeypatch.setattr(
        "app.api.query.retrieve_documents",
        fake_retrieve_factory(
            department.id
        ),
    )

    class FakeProvider:
        def generate(
            self,
            *,
            query,
            context,
        ):
            raise AssertionError

        def generate_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            raise AssertionError

        def stream(
            self,
            *,
            query,
            context,
        ):
            yield "stateless"

        def stream_conversational(
            self,
            *,
            query,
            context,
            previous_user_messages,
        ):
            raise AssertionError

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
            "/query/stream",
            json={
                "query": "Answer without a conversation.",
            },
        )

        assert response.status_code == 200

        assert (
            db_session.query(
                ConversationMessage
            ).count()
            == 0
        )

    finally:
        clear_app()
