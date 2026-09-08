from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Conversation,
    ConversationMessage,
    ConversationMessageRole,
    User,
)


def normalize_conversation_title(
    title: str | None,
) -> str | None:
    if title is None:
        return None

    normalized = title.strip()

    return normalized or None


def create_conversation(
    db: Session,
    *,
    current_user: User,
    title: str | None = None,
) -> Conversation:
    conversation = Conversation(
        user_id=current_user.id,
        title=normalize_conversation_title(title),
    )

    db.add(conversation)
    db.flush()

    return conversation


def get_owned_conversation(
    db: Session,
    *,
    conversation_id: int,
    current_user: User,
) -> Conversation:
    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
        .first()
    )

    if conversation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )

    return conversation


def list_owned_conversations(
    db: Session,
    *,
    current_user: User,
    limit: int,
    offset: int,
) -> tuple[list[Conversation], int]:
    base_query = (
        db.query(Conversation)
        .filter(
            Conversation.user_id == current_user.id,
        )
    )

    total = (
        base_query.with_entities(
            func.count(Conversation.id)
        )
        .scalar()
        or 0
    )

    conversations = (
        base_query
        .order_by(
            Conversation.updated_at.desc(),
            Conversation.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    return conversations, total


def add_conversation_message(
    db: Session,
    *,
    conversation: Conversation,
    role: ConversationMessageRole,
    content: str,
) -> ConversationMessage:
    normalized_content = content.strip()

    if not normalized_content:
        raise ValueError(
            "Conversation message content cannot be empty"
        )

    message = ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=normalized_content,
    )

    db.add(message)

    conversation.updated_at = datetime.now(
        timezone.utc
    )

    db.flush()

    return message


def get_recent_user_messages(
    db: Session,
    *,
    conversation: Conversation,
    limit: int = 8,
) -> list[str]:
    if limit < 1:
        return []

    messages = (
        db.query(ConversationMessage)
        .filter(
            ConversationMessage.conversation_id
            == conversation.id,
            ConversationMessage.role
            == ConversationMessageRole.USER,
        )
        .order_by(
            ConversationMessage.id.desc()
        )
        .limit(limit)
        .all()
    )

    messages.reverse()

    return [
        message.content
        for message in messages
    ]


def delete_conversation(
    db: Session,
    *,
    conversation: Conversation,
) -> None:
    db.delete(conversation)
    db.flush()
