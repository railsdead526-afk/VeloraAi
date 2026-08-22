"""Data portability export (UU PDP No. 27/2022, right to portability).

Produces a complete, machine-readable copy of everything the service holds
about one user.

Two rules govern what goes in:

  1. Everything the user supplied or generated is included, so the export is
     genuinely portable rather than a token gesture.
  2. Nothing that would weaken security if the file leaked is included. Password
     hashes, encrypted third-party tokens, refresh-token digests, and embedding
     vectors are deliberately excluded. An export lands in inboxes and download
     folders; treat it as public.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.plans import get_plan_policy
from app.models.ai_usage import AIUsage
from app.models.audit_log import AuditLog
from app.models.billing import Payment, Subscription
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.integration import UserIntegration
from app.models.message import Message
from app.models.user import User

EXPORT_FORMAT_VERSION = "1.0"

#: Audit history is capped so a long-lived account cannot generate an
#: unbounded response. The full history stays available on request.
AUDIT_LOG_LIMIT = 5000


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.isoformat()


def build_export(db: Session, *, user: User) -> dict[str, Any]:
    """Assemble the portable archive for `user`."""
    conversations = list(
        db.execute(
            select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.id)
        ).scalars()
    )
    conversation_ids = [conversation.id for conversation in conversations]

    messages_by_conversation: dict[int, list[Message]] = {cid: [] for cid in conversation_ids}
    if conversation_ids:
        for message in db.execute(
            select(Message)
            .where(Message.conversation_id.in_(conversation_ids))
            .order_by(Message.conversation_id, Message.id)
        ).scalars():
            messages_by_conversation[message.conversation_id].append(message)

    documents = list(
        db.execute(
            select(Document).where(Document.user_id == user.id).order_by(Document.id)
        ).scalars()
    )
    subscriptions = list(
        db.execute(
            select(Subscription).where(Subscription.user_id == user.id).order_by(Subscription.id)
        ).scalars()
    )
    payments = list(
        db.execute(select(Payment).where(Payment.user_id == user.id).order_by(Payment.id)).scalars()
    )
    integrations = list(
        db.execute(
            select(UserIntegration)
            .where(UserIntegration.user_id == user.id)
            .order_by(UserIntegration.provider)
        ).scalars()
    )
    usage = list(
        db.execute(select(AIUsage).where(AIUsage.user_id == user.id).order_by(AIUsage.id)).scalars()
    )
    audit_events = list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.user_id == user.id)
            .order_by(AuditLog.id.desc())
            .limit(AUDIT_LOG_LIMIT)
        ).scalars()
    )

    policy = get_plan_policy(user.role)

    return {
        "export_format_version": EXPORT_FORMAT_VERSION,
        "generated_at": _iso(datetime.now(UTC)),
        "service": settings.app_name,
        "notice": (
            "This archive contains your personal data. Password hashes, encrypted "
            "third-party tokens, and session credentials are intentionally excluded. "
            "Store it securely."
        ),
        "account": {
            "id": user.id,
            "email": user.email,
            "is_active": bool(user.is_active),
            "plan": user.role,
            "email_verified_at": _iso(user.email_verified_at),
            "password_changed_at": _iso(user.password_changed_at),
            "last_login_at": _iso(user.last_login_at),
            "created_at": _iso(user.created_at),
            "updated_at": _iso(user.updated_at),
            "deleted_at": _iso(user.deleted_at),
        },
        "plan_limits": {
            "monthly_token_limit": policy.monthly_token_limit,
            "monthly_request_limit": policy.monthly_request_limit,
            "daily_request_limit": policy.daily_request_limit,
        },
        "conversations": [
            {
                "id": conversation.id,
                "title": conversation.title,
                "created_at": _iso(conversation.created_at),
                "messages": [
                    {
                        "id": message.id,
                        "role": message.role,
                        "content": message.content,
                        "created_at": _iso(message.created_at),
                    }
                    for message in messages_by_conversation.get(conversation.id, [])
                ],
            }
            for conversation in conversations
        ],
        "documents": [
            {
                "id": document.id,
                "name": document.name,
                "source": document.source,
                "mime_type": document.mime_type,
                "status": document.status,
                # The original text is the user's own content, so it belongs in
                # the export. Embedding vectors are derived and are not portable.
                "text": document.raw_text,
                "created_at": _iso(document.created_at),
                "last_indexed_at": _iso(document.last_indexed_at),
            }
            for document in documents
        ],
        "subscriptions": [
            {
                "id": subscription.id,
                "plan": subscription.plan,
                "provider": subscription.provider,
                "status": subscription.status,
                "current_period_start": _iso(subscription.current_period_start),
                "current_period_end": _iso(subscription.current_period_end),
                "grace_until": _iso(subscription.grace_until),
                "cancel_at_period_end": bool(subscription.cancel_at_period_end),
                "canceled_at": _iso(subscription.canceled_at),
                "created_at": _iso(subscription.created_at),
            }
            for subscription in subscriptions
        ],
        "payments": [
            {
                "id": payment.id,
                "invoice_number": payment.invoice_number,
                "provider": payment.provider,
                "provider_order_id": payment.provider_order_id,
                "plan": payment.plan,
                "amount": payment.amount,
                "tax_amount": payment.tax_amount,
                "currency": payment.currency,
                "status": payment.status,
                "payment_type": payment.payment_type,
                "refund_amount": payment.refund_amount,
                "paid_at": _iso(payment.paid_at),
                "refunded_at": _iso(payment.refunded_at),
                "created_at": _iso(payment.created_at),
            }
            for payment in payments
        ],
        "integrations": [
            {
                "provider": integration.provider,
                "display_name": integration.display_name,
                # Fingerprint only. The token itself is never exportable.
                "secret_fingerprint": integration.secret_fingerprint,
                "status": integration.status,
                "last_used_at": _iso(integration.last_used_at),
                "created_at": _iso(integration.created_at),
            }
            for integration in integrations
        ],
        "ai_usage": [
            {
                "id": record.id,
                "conversation_id": record.conversation_id,
                "provider": record.provider,
                "model": record.model,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "total_tokens": record.total_tokens,
                "created_at": _iso(record.created_at),
            }
            for record in usage
        ],
        "audit_log": [
            {
                "event": event.event,
                "status": event.status,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "created_at": _iso(event.created_at),
            }
            for event in reversed(audit_events)
        ],
    }


def render_export(db: Session, *, user: User) -> tuple[str, str]:
    """Return `(filename, json_body)` for download."""
    payload = build_export(db, user=user)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    filename = f"veloraai-export-{user.id}-{stamp}.json"
    return filename, json.dumps(payload, ensure_ascii=False, indent=2)
