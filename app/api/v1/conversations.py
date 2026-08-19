from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.crud.ai_usage import record_ai_usage
from app.crud.conversation import create_conversation, delete_conversation, get_conversation_by_id, get_user_conversations, update_conversation_title
from app.crud.message import create_message, get_messages_by_conversation
from app.schemas.conversation import ConversationCreate, ConversationResponse, ConversationUpdate
from app.schemas.message import MessageCreate, MessageResponse, ChatReplyResponse
from app.services.ai_service import generate_ai_reply_from_history

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_new_conversation(payload: ConversationCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return create_conversation(db, user_id=current_user.id, title=payload.title or "New Chat")


@router.get("", response_model=list[ConversationResponse])
def list_my_conversations(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return get_user_conversations(db, current_user.id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(conversation_id: int, payload: ConversationUpdate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return update_conversation_title(db, conversation, payload.title)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_conversation(conversation_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    delete_conversation(db, conversation)
    return None


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_conversation_messages(conversation_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return get_messages_by_conversation(db, conversation_id)


@router.post("/{conversation_id}/messages", response_model=ChatReplyResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.rate_limit_chat)
def send_message(request: Request, conversation_id: int, payload: MessageCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    user_message = create_message(db, conversation_id=conversation_id, role="user", content=payload.content, commit=False)
    history = get_messages_by_conversation(db, conversation_id)
    history_payload = [{"role": message.role, "content": message.content} for message in history]

    try:
        assistant_reply = generate_ai_reply_from_history(history_payload)
        assistant_message = create_message(db, conversation_id=conversation_id, role="assistant", content=assistant_reply, commit=False)
        input_tokens = max(1, sum(len(item["content"]) for item in history_payload) // 4)
        output_tokens = max(1, len(assistant_reply) // 4)
        record_ai_usage(
            db,
            user_id=current_user.id,
            conversation_id=conversation_id,
            provider=settings.ai_provider,
            model=settings.openai_model if settings.ai_provider == "openai" else "mock",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            commit=False,
        )
        db.commit()
        db.refresh(user_message)
        db.refresh(assistant_message)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to complete the request")

    return {"user_message": user_message, "assistant_message": assistant_message}
