"""Outbound notifications.

Delivery goes through a pluggable sender. When SMTP is configured the built-in
transport is used; otherwise the message is logged instead of silently
disappearing, and in non-production the token is included so local flows can be
completed. `set_email_sender` remains the seam for a hosted provider
(SendGrid, SES, Resend) or a test double.
"""

from __future__ import annotations

import json
import logging
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage

from app.core.config import settings
from app.core.observability import get_request_id

logger = logging.getLogger("veloraai.notifications")

#: Signature: (to, subject, body) -> None
EmailSender = Callable[[str, str, str], None]

_sender: EmailSender | None = None


class EmailDeliveryError(RuntimeError):
    """Raised when a configured transport could not deliver a message."""


def set_email_sender(sender: EmailSender | None) -> None:
    """Install the production email transport (or a test double)."""
    global _sender
    _sender = sender


def smtp_sender(to: str, subject: str, body: str) -> None:
    """Minimal, dependency-free SMTP transport.

    Uses implicit TLS on port 465 and STARTTLS otherwise. Certificate
    verification is always on; there is no opt-out, because an unverified
    channel would leak password-reset tokens.
    """
    if not settings.smtp_host:
        raise EmailDeliveryError("SMTP_HOST is not configured")

    message = EmailMessage()
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    timeout = settings.smtp_timeout_seconds

    try:
        if settings.smtp_use_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=timeout, context=context
            ) as client:
                _smtp_login_and_send(client, message)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout) as client:
                client.ehlo()
                if settings.smtp_use_starttls:
                    client.starttls(context=context)
                    client.ehlo()
                _smtp_login_and_send(client, message)
    except (smtplib.SMTPException, OSError) as exc:
        # Never include the body: it carries reset and verification tokens.
        raise EmailDeliveryError(f"SMTP delivery failed: {type(exc).__name__}") from exc


def _smtp_login_and_send(client: smtplib.SMTP, message: EmailMessage) -> None:
    if settings.smtp_username:
        client.login(settings.smtp_username, settings.smtp_password)
    client.send_message(message)


def active_sender() -> EmailSender | None:
    """Resolve the transport: an installed sender first, then SMTP if set up."""
    if _sender is not None:
        return _sender
    if settings.smtp_host:
        return smtp_sender
    return None


def _deliver(*, to: str, subject: str, body: str, event: str, token: str | None) -> None:
    """Send the message, and never let a delivery failure break the caller.

    Registration and password-reset endpoints must not 500 because a mail
    server is down, and password reset must stay non-enumerable. Failures are
    logged for alerting instead.
    """
    sender = active_sender()
    delivered = "logged"
    error: str | None = None

    if sender is not None:
        try:
            sender(to, subject, body)
            delivered = "sent"
        except Exception as exc:  # delivery must never break the request
            delivered = "failed"
            error = type(exc).__name__
            logger.exception("email delivery failed event=%s", event)

    payload = {
        "event": event,
        "request_id": get_request_id(),
        "to": to,
        "subject": subject,
        "delivery": delivered,
    }
    if error:
        payload["error"] = error
    # Only ever expose the token when nothing could deliver it and we are not
    # in production, so a local developer can still complete the flow.
    if token and delivered == "logged" and not settings.is_production:
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
