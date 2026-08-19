import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
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
from app.schemas.message import MessageCreate, MessageResponse, ChatReplyResponse
from app.services.ai_service import generate_ai_reply_from_history, stream_ai_reply_from_history
from app.services.ai_tool_loop import generate_ai_reply_with_tools, generate_ai_reply_with_tools_async
from app.services.quota_service import QuotaExceededError, enforce_plan_quota
from app.services.rag_service import RAGError, build_context, retrieve_chunks
from app.tools.bootstrap import get_registry

router = APIRouter(prefix="/conversations", tags=["conversations"])


def enforce_user_plan_quota(db: Session, user) -> None:
    try:
        enforce_plan_quota(
            db,
            user_id=user.id,
            policy=get_plan_policy(getattr(user, "role", None)),
        )
    except QuotaExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc


def _history_with_rag_context(db: Session, *, user_id: int, history_payload: list[dict], query: str, use_rag: bool) -> list[dict]:
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

    enforce_user_plan_quota(db, current_user)
    user_message = create_message(db, conversation_id=conversation_id, role="user", content=payload.content, commit=False)
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
            ai_result = generate_ai_reply_with_tools(
                history_payload,
                plan=getattr(current_user, "role", "free"),
                confirmed=payload.confirm_tools,
                registry=get_registry(),
            )
        else:
            ai_result = generate_ai_reply_from_history(history_payload)

        assistant_message = create_message(db, conversation_id=conversation_id, role="assistant", content=ai_result.content, commit=False)
        input_tokens = ai_result.input_tokens
        output_tokens = ai_result.output_tokens
        if input_tokens is None or output_tokens is None:
            raise RuntimeError("AI provider did not return token usage")
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
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to complete the request") from exc

    return {"user_message": user_message, "assistant_message": assistant_message}


@router.post("/{conversation_id}/messages/stream")
@limiter.limit(settings.rate_limit_chat)
def stream_message(request: Request, conversation_id: int, payload: MessageCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    conversation = get_conversation_by_id(db, conversation_id)
    if not conversation or conversation.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    enforce_user_plan_quota(db, current_user)
    user_message = create_message(db, conversation_id=conversation_id, role="user", content=payload.content, commit=False)
    history = get_messages_by_conversation(db, conversation_id)
    history_payload = [{"role": message.role, "content": message.content} for message in history]
    history_payload = _history_with_rag_context(
        db,
        user_id=current_user.id,
        history_payload=history_payload,
        query=payload.content,
        use_rag=payload.use_rag,
    )
    usage = {}
    user_id = current_user.id

    async def event_stream():
        chunks: list[str] = []
        try:
            if settings.ai_provider in {"openai", "llama"}:
                ai_result = await generate_ai_reply_with_tools_async(
                    history_payload,
                    plan=getattr(current_user, "role", "free"),
                    confirmed=payload.confirm_tools,
                    registry=get_registry(),
                )
                usage.update({
                    "input_tokens": ai_result.input_tokens,
                    "output_tokens": ai_result.output_tokens,
                    "model": ai_result.model,
                })
                for chunk in ai_result.content.split(" "):
                    chunks.append(chunk)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk + ' '}, ensure_ascii=False)}\n\n"
            else:
                async for chunk in stream_ai_reply_from_history(history_payload, usage):
                    chunks.append(chunk)
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk}, ensure_ascii=False)}\n\n"

            assistant_reply = "".join(chunks).strip()
            if not assistant_reply:
                raise RuntimeError("AI provider returned an empty response")
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            model = usage.get("model")
            if input_tokens is None or output_tokens is None or not model:
                raise RuntimeError("AI provider did not return token usage")

            assistant_message = create_message(db, conversation_id=conversation_id, role="assistant", content=assistant_reply, commit=False)
            record_ai_usage(
                db,
                user_id=user_id,
                conversation_id=conversation_id,
                provider="mock" if model == "mock" else settings.ai_provider,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                commit=False,
            )
            db.commit()
            db.refresh(user_message)
            db.refresh(assistant_message)
            yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            db.rollback()
            raise
        except RuntimeError as exc:
            db.rollback()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, ensure_ascii=False)}\n\n"
        except Exception:
            db.rollback()
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Unable to complete the request'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )