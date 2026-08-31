import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.crud.ai_usage import record_ai_usage
from app.crud.conversation import get_conversation_by_id
from app.crud.message import create_message
from app.schemas.message import MessageCreate
from app.services.agent_context import (
    build_agent_history,
    enforce_user_plan_quota,
    reserve_user_plan_request_quota,
)
from app.services.ai_service import stream_ai_reply_from_history
from app.services.ai_tool_stream import stream_ai_reply_with_tools
from app.services.audit_service import record_audit_event_best_effort
from app.services.quota_service import (
    QuotaExceededError,
    complete_request_reservation,
    release_request_reservation,
)
from app.services.rag_service import RAGError
from app.tools.bootstrap import get_registry

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("/{conversation_id}/messages/stream")
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

    reservation_id: int | None = None
    try:
        reservation_id = reserve_user_plan_request_quota(db, current_user)
        history_payload = build_agent_history(
            db,
            conversation_id=conversation_id,
            user_id=current_user.id,
            query=payload.content,
            use_rag=payload.use_rag,
        )
    except QuotaExceededError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except RAGError as exc:
        db.rollback()
        if reservation_id is not None:
            release_request_reservation(db, reservation_id)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="RAG retrieval is temporarily unavailable",
        ) from exc

    user_id = current_user.id
    plan = getattr(current_user, "role", "free")
    record_audit_event_best_effort(
        user_id=user_id,
        event="agent_request_started",
        resource_type="conversation",
        resource_id=str(conversation_id),
        metadata={"plan": plan, "rag": bool(payload.use_rag)},
    )

    async def event_stream():
        chunks: list[str] = []
        usage = {"input_tokens": None, "output_tokens": None, "model": None}
        confirmation_required = False
        try:
            if settings.ai_provider in {"openai", "llama", "gemini"}:
                async for event in stream_ai_reply_with_tools(
                    history_payload,
                    db=db,
                    plan=plan,
                    confirmed=False,
                    registry=get_registry(),
                    user_id=user_id,
                    conversation_id=conversation_id,
                    approved_confirmation_token=payload.tool_confirmation_token,
                ):
                    event_payload = {"type": event.type}
                    if event.content:
                        chunks.append(event.content)
                        event_payload["content"] = event.content
                    if event.name:
                        event_payload["name"] = event.name
                    if event.tool_call_id:
                        event_payload["tool_call_id"] = event.tool_call_id
                    if event.confirmation_token:
                        event_payload["confirmation_token"] = event.confirmation_token
                    if event.type == "tool_start" and event.name:
                        record_audit_event_best_effort(
                            user_id=user_id,
                            event="agent_tool_requested",
                            resource_type="tool",
                            resource_id=event.name,
                        )
                    if event.type == "tool_confirmation_required":
                        confirmation_required = True
                        record_audit_event_best_effort(
                            user_id=user_id,
                            event="agent_tool_confirmation_required",
                            status="pending",
                            resource_type="tool",
                            resource_id=event.name,
                        )
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

            if confirmation_required:
                if reservation_id is not None:
                    release_request_reservation(db, reservation_id)
                    db.commit()
                return

            assistant_reply = "".join(chunks).strip()
            if not assistant_reply:
                raise RuntimeError("AI provider returned an empty response")

            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            model = usage.get("model")
            # Fallback if provider didn't return usage (e.g. Gemini streaming without include_usage)
            if input_tokens is None or output_tokens is None:
                # estimate: ~4 chars per token
                estimated_input = max(1, sum(len(m.get("content", "")) for m in history_payload) // 4)
                estimated_output = max(1, len(assistant_reply) // 4)
                input_tokens = input_tokens if input_tokens is not None else estimated_input
                output_tokens = output_tokens if output_tokens is not None else estimated_output
            if not model:
                model = settings.ai_provider if settings.ai_provider != "mock" else "mock"
                usage["model"] = model

            user_message = create_message(
                db,
                conversation_id=conversation_id,
                role="user",
                content=payload.content,
                commit=False,
            )
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
                check_request_limits=False,
            )
            if reservation_id is not None:
                complete_request_reservation(db, reservation_id)
            db.commit()
            db.refresh(user_message)
            db.refresh(assistant_message)
            record_audit_event_best_effort(
                user_id=user_id,
                event="agent_request_completed",
                resource_type="conversation",
                resource_id=str(conversation_id),
                metadata={"model": model},
            )
            yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_message.id}, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            db.rollback()
            if reservation_id is not None:
                release_request_reservation(db, reservation_id)
                db.commit()
            record_audit_event_best_effort(
                user_id=user_id,
                event="agent_request_failed",
                status="cancelled",
                resource_type="conversation",
                resource_id=str(conversation_id),
            )
            raise
        except QuotaExceededError as exc:
            db.rollback()
            if reservation_id is not None:
                release_request_reservation(db, reservation_id)
                db.commit()
            record_audit_event_best_effort(
                user_id=user_id,
                event="agent_request_failed",
                status="quota_exceeded",
                resource_type="conversation",
                resource_id=str(conversation_id),
            )
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, ensure_ascii=False)}\n\n"
        except RuntimeError as exc:
            db.rollback()
            if reservation_id is not None:
                release_request_reservation(db, reservation_id)
                db.commit()
            record_audit_event_best_effort(
                user_id=user_id,
                event="agent_request_failed",
                status="provider_or_runtime_error",
                resource_type="conversation",
                resource_id=str(conversation_id),
            )
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)}, ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            db.rollback()
            if reservation_id is not None:
                release_request_reservation(db, reservation_id)
                db.commit()
            record_audit_event_best_effort(
                user_id=user_id,
                event="agent_request_failed",
                status=f"http_{exc.status_code}",
                resource_type="conversation",
                resource_id=str(conversation_id),
            )
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc.detail)}, ensure_ascii=False)}\n\n"
        except Exception:
            db.rollback()
            if reservation_id is not None:
                release_request_reservation(db, reservation_id)
                db.commit()
            record_audit_event_best_effort(
                user_id=user_id,
                event="agent_request_failed",
                status="internal_error",
                resource_type="conversation",
                resource_id=str(conversation_id),
            )
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
