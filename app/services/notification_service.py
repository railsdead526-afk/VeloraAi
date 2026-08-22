"""Outbound notifications.

There is deliberately no SMTP client wired up yet. Rather than pretend an
email was sent, this module logs a structured, redacted event and exposes a
single seam (`set_email_sender`) for the real provider to be plugged in.

In non-production environments the token is included in the log so the flow can
actually be completed locally. In production it never is.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from app.core.config import settings
from app.core.observability import get_request_id

logger = logging.getLogger("veloraai.notifications")

#: Signature: (to, subject, body) -> None
EmailSender = Callable[[str, str, str], None]

_sender: EmailSender | None = None


def set_email_sender(sender: EmailSender | None) -> None:
    """Install the production email transport (or a test double)."""
    global _sender
    _sender = sender


def _deliver(*, to: str, subject: str, body: str, event: str, token: str | None) -> None:
    if _sender is not None:
        _sender(to, subject, body)
        delivered = "sent"
    else:
        delivered = "logged"

    payload = {
        "event": event,
        "request_id": get_request_id(),
        "to": to,
        "subject": subject,
        "delivery": delivered,
    }
    if token and not settings.is_production:
        payload["dev_token"] = token
    logger.info(json.dumps(payload, separators=(",", ":")))


def send_verification_email(*, email: str, token: str) -> None:
    link = f"{settings.frontend_base_url}/verify-email?token={token}"
    _deliver(
        to=email,
        subject=f"Verify your {settings.app_name} email address",
        body=(
            f"Confirm your address to activate your {settings.app_name} account:\n\n{link}\n\n"
            f"This link expires in {settings.email_verification_ttl_hours} hours."
        ),
        event="email.verification",
        token=token,
    )


def send_password_reset_email(*, email: str, token: str) -> None:
    link = f"{settings.frontend_base_url}/reset-password?token={token}"
    _deliver(
        to=email,
        subject=f"Reset your {settings.app_name} password",
        body=(
            f"Use this link to choose a new password:\n\n{link}\n\n"
            f"It expires in {settings.password_reset_ttl_minutes} minutes. "
            "If you did not request this, no action is needed."
        ),
        event="email.password_reset",
        token=token,
    )


def send_subscription_expiring_email(*, email: str, plan: str, days_left: int) -> None:
    _deliver(
        to=email,
        subject=f"Your {settings.app_name} {plan.upper()} plan renews soon",
        body=(
            f"Your {plan.upper()} plan ends in {days_left} day(s). "
            f"Renew at {settings.frontend_base_url}/billing to avoid interruption."
        ),
        event="email.subscription_expiring",
        token=None,
    )


def send_subscription_downgraded_email(*, email: str, plan: str) -> None:
    _deliver(
        to=email,
        subject=f"Your {settings.app_name} {plan.upper()} plan has ended",
        body=(
            f"Your {plan.upper()} plan has ended and your account moved to the Free plan. "
            f"Reactivate any time at {settings.frontend_base_url}/billing."
        ),
        event="email.subscription_downgraded",
        token=None,
    )
