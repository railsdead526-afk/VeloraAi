from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.crud.conversation import (
    create_conversation,
    delete_conversation,
    get_conversation_by_id,
    get_user_conversations,
    update_conversation_title,
)
from app.crud.message import (
    create_message,
    get_messages_by_conversation,
)
from app.schemas.conversation import (
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import MessageCreate, MessageResponse, ChatReplyResponse
from app.services.ai_service import generate_ai_reply_from_history

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_new_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_conversation(
        db,
        user_id=current_user.id,
        title=payload.title or "New Chat"
    )


@router.get("", response_model=list[ConversationResponse])
def list_my_conversations(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_user_conversations(db, current_user.id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conversation = get_conversation_by_id(db, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    return update_conversation_title(db, conversation, payload.title)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conversation = get_conversation_by_id(db, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    delete_conversation(db, conversation)
    return None


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conversation = get_conversation_by_id(db, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    return get_messages_by_conversation(db, conversation_id)


@router.post("/{conversation_id}/messages", response_model=ChatReplyResponse, status_code=status.HTTP_201_CREATED)
def send_message(
    conversation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conversation = get_conversation_by_id(db, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    user_message = create_message(
        db,
        conversation_id=conversation_id,
        role="user",
        content=payload.content
    )

    history = get_messages_by_conversation(db, conversation_id)

    history_payload = [
        {
            "role": message.role,
            "content": message.content
        }
        for message in history
    ]

    assistant_reply = generate_ai_reply_from_history(history_payload)

    assistant_message = create_message(
        db,
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_reply
    )

    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
    }

