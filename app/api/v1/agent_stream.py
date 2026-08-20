import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.rate_limit import limiter
from app.crud.ai_usage import record_ai_usage
from app.crud.conversation import get_conversation_by_id
from app.crud.message import create_message
from app.schemas.message import MessageCreate
from app.services.agent_context import build_agent_history, enforce_user_plan_quota
from app.services.ai_service import stream_ai_reply_from_history
from app.services.ai_tool_stream import stream_ai_reply_with_tools
from app.tools.bootstrap import get_registry
from app.core.database import get_db

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/{conversation_id}/messages/stream-native")
@limiter.limit(settings.rate_limit_chat)
def stream_native_message(
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
        db,
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
        commit=False,
    )
    history_payload = build_agent_history(
        db,
        conversation_id=conversation_id,
        user_id=current_user.id,
        query=payload.content,
        use_rag=payload.use_rag,
    )
    user_id = current_user.id
    plan = getattr(current_user, "role", "free")

    async def event_stream():
        chunks: list[str] = []
        usage = {"input_tokens": None, "output_tokens": None, "model": None}
        try:
            if settings.ai_provider in {"openai", "llama"}:
                async for event in stream_ai_reply_with_tools(
                    history_payload,
                    plan=plan,
                    confirmed=payload.confirm_tools,
                    registry=get_registry(),
                ):
                    event_payload = {"type": event.type}
                    if event.content:
                        chunks.append(event.content)
                        event_payload["content"] = event.content
                    if event.name:
                        event_payload["name"] = event.name
                    if event.tool_call_id:
                        event_payload["tool_call_id"] = event.tool_call_id
                    if event.type == "done":
                        usage.update(
                            {
                                "input_tokens": event.input_tokens,
                                "output_tokens": event.output_tokens,
                                "model": event.model,
                            }
                        )
                    yield f"data: {json.dumps(event_payload, ensure_ascii=False)}\n\n"
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

            assistant_message = create_message(
                db,
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_reply,
                commit=False,
            )
            record_ai_usage(
                db,
                user_id=user_id,
                conversation_id=conversation_id,
                provider="mock" if model == "mock" else settings.ai_provider,
                model=model,
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                commit=False,
            )
            enforce_user_plan_quota(
                db,
                current_user,
                additional_tokens=int(input_tokens) + int(output_tokens),
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
        except HTTPException as exc:
            db.rollback()
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc.detail)}, ensure_ascii=False)}\n\n"
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
