from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.models import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationListResponse,
    ConversationMessageResponse,
    ConversationSummary,
)
from app.services.conversation import (
    create_conversation,
    delete_conversation,
    get_owned_conversation,
    list_owned_conversations,
)


router = APIRouter(
    prefix="/conversations",
    tags=["Conversations"],
)


@router.post(
    "/",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_endpoint(
    request: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = create_conversation(
        db,
        current_user=current_user,
        title=request.title,
    )

    db.commit()
    db.refresh(conversation)

    return ConversationSummary(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get(
    "/",
    response_model=ConversationListResponse,
)
def list_conversations_endpoint(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversations, total = list_owned_conversations(
        db,
        current_user=current_user,
        limit=limit,
        offset=offset,
    )

    return ConversationListResponse(
        items=[
            ConversationSummary(
                id=conversation.id,
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
            )
            for conversation in conversations
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{conversation_id}",
    response_model=ConversationDetail,
)
def get_conversation_endpoint(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        current_user=current_user,
    )

    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[
            ConversationMessageResponse(
                id=message.id,
                role=message.role.value,
                content=message.content,
                created_at=message.created_at,
            )
            for message in conversation.messages
        ],
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation_endpoint(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        current_user=current_user,
    )

    delete_conversation(
        db,
        conversation=conversation,
    )

    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
