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
from app.services.conversation import add_conversation_message


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


def create_department(
    db_session,
    name: str,
) -> Department:
    department = Department(name=name)
    db_session.add(department)
    db_session.flush()
    return department


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


def test_user_can_create_and_read_conversation(
    db_session,
):
    department = create_department(
        db_session,
        "Conversation-Engineering",
    )

    user = create_user(
        db_session,
        email="conversation-owner@example.com",
        department_id=department.id,
    )

    db_session.commit()

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        create_response = client.post(
            "/conversations/",
            json={
                "title": "Engineering discussion"
            },
        )

        assert create_response.status_code == 201

        created = create_response.json()

        assert created["title"] == (
            "Engineering discussion"
        )
        assert created["id"] > 0

        conversation = db_session.get(
            Conversation,
            created["id"],
        )

        assert conversation is not None

        add_conversation_message(
            db_session,
            conversation=conversation,
            role=ConversationMessageRole.USER,
            content="What is our release process?",
        )
        add_conversation_message(
            db_session,
            conversation=conversation,
            role=ConversationMessageRole.ASSISTANT,
            content="The release process has four checks.",
        )
        db_session.commit()

        response = client.get(
            f"/conversations/{conversation.id}"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["id"] == conversation.id
        assert len(body["messages"]) == 2
        assert body["messages"][0]["role"] == "user"
        assert body["messages"][1]["role"] == "assistant"
        assert (
            body["messages"][0]["content"]
            == "What is our release process?"
        )

    finally:
        app.dependency_overrides.clear()


def test_user_can_list_only_owned_conversations(
    db_session,
):
    department = create_department(
        db_session,
        "Conversation-Finance",
    )

    owner = create_user(
        db_session,
        email="conversation-list-owner@example.com",
        department_id=department.id,
    )

    other_user = create_user(
        db_session,
        email="conversation-list-other@example.com",
        department_id=department.id,
    )

    owner_conversation = Conversation(
        user_id=owner.id,
        title="Owned conversation",
    )

    other_conversation = Conversation(
        user_id=other_user.id,
        title="Other conversation",
    )

    db_session.add_all(
        [
            owner_conversation,
            other_conversation,
        ]
    )

    db_session.commit()

    configure_app(
        db_session,
        owner,
    )

    client = TestClient(app)

    try:
        response = client.get(
            "/conversations/"
        )

        assert response.status_code == 200

        body = response.json()

        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["id"] == (
            owner_conversation.id
        )

    finally:
        app.dependency_overrides.clear()


def test_user_cannot_access_another_users_conversation(
    db_session,
):
    department = create_department(
        db_session,
        "Conversation-Security",
    )

    owner = create_user(
        db_session,
        email="conversation-security-owner@example.com",
        department_id=department.id,
    )

    attacker = create_user(
        db_session,
        email="conversation-security-attacker@example.com",
        department_id=department.id,
    )

    conversation = Conversation(
        user_id=owner.id,
        title="Private conversation",
    )

    db_session.add(conversation)
    db_session.commit()

    configure_app(
        db_session,
        attacker,
    )

    client = TestClient(app)

    try:
        response = client.get(
            f"/conversations/{conversation.id}"
        )

        assert response.status_code == 404
        assert response.json()["detail"] == (
            "Conversation not found"
        )

    finally:
        app.dependency_overrides.clear()


def test_user_cannot_delete_another_users_conversation(
    db_session,
):
    department = create_department(
        db_session,
        "Conversation-Delete-Security",
    )

    owner = create_user(
        db_session,
        email="conversation-delete-owner@example.com",
        department_id=department.id,
    )

    attacker = create_user(
        db_session,
        email="conversation-delete-attacker@example.com",
        department_id=department.id,
    )

    conversation = Conversation(
        user_id=owner.id,
        title="Protected conversation",
    )

    db_session.add(conversation)
    db_session.commit()

    configure_app(
        db_session,
        attacker,
    )

    client = TestClient(app)

    try:
        response = client.delete(
            f"/conversations/{conversation.id}"
        )

        assert response.status_code == 404

        db_session.expire_all()

        assert (
            db_session.get(
                Conversation,
                conversation.id,
            )
            is not None
        )

    finally:
        app.dependency_overrides.clear()


def test_user_can_delete_owned_conversation_and_messages_cascade(
    db_session,
):
    department = create_department(
        db_session,
        "Conversation-Cascade",
    )

    user = create_user(
        db_session,
        email="conversation-cascade@example.com",
        department_id=department.id,
    )

    conversation = Conversation(
        user_id=user.id,
        title="To delete",
    )

    db_session.add(conversation)
    db_session.flush()

    add_conversation_message(
        db_session,
        conversation=conversation,
        role=ConversationMessageRole.USER,
        content="Delete me",
    )

    db_session.commit()

    conversation_id = conversation.id

    configure_app(
        db_session,
        user,
    )

    client = TestClient(app)

    try:
        response = client.delete(
            f"/conversations/{conversation_id}"
        )

        assert response.status_code == 204

        db_session.expire_all()

        assert (
            db_session.get(
                Conversation,
                conversation_id,
            )
            is None
        )

        remaining_messages = (
            db_session.query(
                ConversationMessage
            )
            .filter(
                ConversationMessage.conversation_id
                == conversation_id
            )
            .all()
        )

        assert remaining_messages == []

    finally:
        app.dependency_overrides.clear()
