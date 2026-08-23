from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.plans import get_plan_policy
from app.core.rate_limit import limiter
from app.crud.ai_usage import record_ai_usage
from app.crud.conversation import (
    create_conversation,
    delete_conversation,
    get_conversation_by_id,
    get_user_conversations,
    update_conversation_title,
)
from app.crud.message import create_message, get_messages_by_conversation
from app.models.document import Document
from app.schemas.conversation import ConversationCreate, ConversationResponse, ConversationUpdate
from app.schemas.message import ChatReplyResponse, MessageCreate, MessageResponse
from app.services.ai_service import generate_ai_reply_from_history
from app.services.ai_tool_loop import (
    generate_ai_reply_with_tools,
)
from app.services.quota_service import QuotaExceededError, enforce_plan_quota
from app.services.rag_service import RAGError, build_context, retrieve_chunks
from app.tools.bootstrap import get_registry
from app.tools.credentials import user_credential_scope

router = APIRouter(prefix="/conversations", tags=["conversations"])


def enforce_user_plan_quota(db: Session, user, *, additional_tokens: int = 0) -> None:
    try:
        enforce_plan_quota(
            db,
            user_id=user.id,
            policy=get_plan_policy(getattr(user, "role", None)),
            additional_tokens=additional_tokens,
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc


def _history_with_rag_context(
    db: Session, *, user_id: int, history_payload: list[dict], query: str, use_rag: bool
) -> list[dict]:
    if not use_rag:
        return history_payload

    has_documents = (
        db.query(Document.id)
        .filter(Document.user_id == user_id, Document.status == "ready")
        .first()
        is not None
    )
    if not has_documents:
        return history_payload

    try:
        results = retrieve_chunks(db, user_id=user_id, query=query, limit=5)
    except RAGError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG retrieval is temporarily unavailable",
        ) from exc

    context = build_context(results)
    if not context:
        return history_payload

    rag_instruction = (
        "Use the following user-owned document context when it is relevant to the user's request. "
        "Do not claim facts from the context that are not present. If the context is insufficient, say so.\n\n"
        f"{context}"
    )
    return [{"role": "system", "content": rag_instruction}, *history_payload]


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
def create_new_conversation(
    payload: ConversationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_conversation(db, user_id=current_user.id, title=payload.title or "New Chat")


@router.get("/{conversation_id}", response_model=ConversationResponse)
def get_conversation_detail(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conversation = get_conversation_by_id(db, conversation_id)

    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    return conversation


@router.get("", response_model=list[ConversationResponse])
def list_my_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """The CRUD layer always accepted limit/offset, but the endpoint never
    exposed them, so anything past the newest 50 conversations was
    permanently unreachable.
    """
    return get_user_conversations(db, current_user.id, limit=limit, offset=offset)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def rename_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return update_conversation_title(db, conversation, payload.title)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_conversation(
    conversation_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    delete_conversation(db, conversation)
    return None


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
def list_conversation_messages(
    conversation_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)
):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return get_messages_by_conversation(db, conversation_id)


@router.post(
    "/{conversation_id}/messages",
    response_model=ChatReplyResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.rate_limit_chat)
def send_message(
    request: Request,
    conversation_id: int,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    enforce_user_plan_quota(db, current_user)
    user_message = create_message(
        db, conversation_id=conversation_id, role="user", content=payload.content, commit=False
    )
    history = get_messages_by_conversation(db, conversation_id)
    history_payload = [{"role": message.role, "content": message.content} for message in history]
    history_payload = _history_with_rag_context(
        db,
        user_id=current_user.id,
        history_payload=history_payload,
        query=payload.content,
        use_rag=payload.use_rag,
    )

    try:
        if settings.ai_provider in {"openai", "llama"}:
            # Tools authenticate as the requesting user, never as the operator.
            with user_credential_scope(current_user.id):
                ai_result = generate_ai_reply_with_tools(
                    history_payload,
                    plan=getattr(current_user, "role", "free"),
                    confirmed=payload.confirm_tools,
                    registry=get_registry(),
                )
        else:
            ai_result = generate_ai_reply_from_history(history_payload)

        input_tokens = ai_result.input_tokens
        output_tokens = ai_result.output_tokens
        if input_tokens is None or output_tokens is None:
            raise RuntimeError("AI provider did not return token usage")

        enforce_user_plan_quota(
            db,
            current_user,
            additional_tokens=int(input_tokens) + int(output_tokens),
        )

        assistant_message = create_message(
            db,
            conversation_id=conversation_id,
            role="assistant",
            content=ai_result.content,
            commit=False,
        )
        record_ai_usage(
            db,
            user_id=current_user.id,
            conversation_id=conversation_id,
            provider="mock" if ai_result.model == "mock" else settings.ai_provider,
            model=ai_result.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            commit=False,
        )
        db.commit()
        db.refresh(user_message)
        db.refresh(assistant_message)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to complete the request",
        ) from exc

    return {"user_message": user_message, "assistant_message": assistant_message}
