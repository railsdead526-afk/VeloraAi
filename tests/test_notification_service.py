"""Delivery of verification and password-reset email."""

import smtplib
from email.message import EmailMessage

import pytest

from app.core.config import settings
from app.services import notification_service as notifications


@pytest.fixture(autouse=True)
def reset_sender():
    notifications.set_email_sender(None)
    yield
    notifications.set_email_sender(None)


def test_an_installed_sender_receives_the_message():
    sent: list[tuple[str, str, str]] = []
    notifications.set_email_sender(lambda to, subject, body: sent.append((to, subject, body)))

    notifications.send_verification_email(email="user@example.com", token="tok-123")

    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "user@example.com"
    assert "verify" in subject.lower()
    assert "tok-123" in body


def test_reset_email_carries_a_usable_link(monkeypatch):
    monkeypatch.setattr(settings, "frontend_base_url", "https://app.example.com")
    sent: list[str] = []
    notifications.set_email_sender(lambda to, subject, body: sent.append(body))

    notifications.send_password_reset_email(email="user@example.com", token="reset-abc")

    assert "https://app.example.com/reset-password?token=reset-abc" in sent[0]


def test_delivery_failure_never_propagates_to_the_caller():
    """A dead mail server must not turn registration into a 500."""

    def broken(to, subject, body):
        raise smtplib.SMTPException("connection refused")

    notifications.set_email_sender(broken)
    notifications.send_verification_email(email="user@example.com", token="tok")


def test_failed_delivery_does_not_leak_the_token_to_logs(caplog):
    def broken(to, subject, body):
        raise smtplib.SMTPException("nope")

    notifications.set_email_sender(broken)
    with caplog.at_level("INFO", logger="veloraai.notifications"):
        notifications.send_password_reset_email(email="user@example.com", token="super-secret-tok")

    combined = " ".join(record.getMessage() for record in caplog.records)
    assert "super-secret-tok" not in combined
    assert '"delivery":"failed"' in combined


def test_dev_token_is_logged_only_when_nothing_can_deliver(caplog, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "smtp_host", "")
    try:
        with caplog.at_level("INFO", logger="veloraai.notifications"):
            notifications.send_verification_email(email="dev@example.com", token="dev-token-xyz")
        combined = " ".join(record.getMessage() for record in caplog.records)
        assert "dev-token-xyz" in combined
    finally:
        monkeypatch.setattr(settings, "app_env", "test")


def test_token_is_never_logged_in_production(caplog, monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "smtp_host", "")
    try:
        with caplog.at_level("INFO", logger="veloraai.notifications"):
            notifications.send_verification_email(email="prod@example.com", token="prod-token-xyz")
        combined = " ".join(record.getMessage() for record in caplog.records)
        assert "prod-token-xyz" not in combined
    finally:
        monkeypatch.setattr(settings, "app_env", "test")


def test_smtp_is_selected_automatically_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    assert notifications.active_sender() is notifications.smtp_sender

    monkeypatch.setattr(settings, "smtp_host", "")
    assert notifications.active_sender() is None


def test_smtp_sender_refuses_to_run_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    with pytest.raises(notifications.EmailDeliveryError, match="SMTP_HOST"):
        notifications.smtp_sender("a@example.com", "subject", "body")


def test_smtp_sender_uses_starttls_and_authenticates(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "mailer")
    monkeypatch.setattr(settings, "smtp_password", "pw")
    monkeypatch.setattr(settings, "smtp_from", "VeloraAi <no-reply@example.com>")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_use_starttls", True)

    calls: list[str] = []
    sent: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls.append(f"connect:{host}:{port}")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            calls.append("ehlo")

        def starttls(self, context=None):
            # A missing TLS context would send reset tokens in the clear.
            assert context is not None
            calls.append("starttls")

        def login(self, username, password):
            calls.append(f"login:{username}")

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    notifications.smtp_sender("user@example.com", "Subject", "Body")

    assert "connect:smtp.example.com:587" in calls
    assert "starttls" in calls
    assert "login:mailer" in calls
    assert sent[0]["To"] == "user@example.com"
    assert sent[0]["From"] == "VeloraAi <no-reply@example.com>"


def test_smtp_sender_supports_implicit_tls(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_port", 465)
    monkeypatch.setattr(settings, "smtp_use_ssl", True)
    monkeypatch.setattr(settings, "smtp_use_starttls", False)
    monkeypatch.setattr(settings, "smtp_username", "")

    used: list[str] = []

    class FakeSMTPS:
        def __init__(self, host, port, timeout=None, context=None):
            assert context is not None
            used.append(f"ssl:{host}:{port}")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_message(self, message):
            used.append("sent")

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPS)
    notifications.smtp_sender("user@example.com", "Subject", "Body")

    assert used == ["ssl:smtp.example.com:465", "sent"]


def test_smtp_errors_are_wrapped_without_exposing_the_body(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.com")
    monkeypatch.setattr(settings, "smtp_use_ssl", False)
    monkeypatch.setattr(settings, "smtp_use_starttls", False)

    class Exploding:
        def __init__(self, *args, **kwargs):
            raise OSError("refused")

    monkeypatch.setattr(smtplib, "SMTP", Exploding)

    with pytest.raises(notifications.EmailDeliveryError) as exc:
        notifications.smtp_sender("user@example.com", "Subject", "token-in-body")

    assert "token-in-body" not in str(exc.value)


# --------------------------------------------------------------------------- #
# Cross-boundary contract
#
# The email templates hardcode frontend paths. If a route is renamed or removed
# on the web side, every verification and reset link silently 404s and nobody
# finds out until users complain. These tests fail the build instead.
# --------------------------------------------------------------------------- #


def _frontend_routes() -> set[str]:
    """Route paths that exist in the Next.js App Router tree."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parents[1] / "web" / "app"
    routes = set()
    for page in app_dir.rglob("page.tsx"):
        relative = page.parent.relative_to(app_dir)
        routes.add("/" + str(relative).replace("\\", "/") if str(relative) != "." else "/")
    return routes


def _captured_link(send, monkeypatch) -> str:
    monkeypatch.setattr(settings, "frontend_base_url", "https://app.example.com")
    bodies: list[str] = []
    notifications.set_email_sender(lambda to, subject, body: bodies.append(body))
    send()
    return bodies[0]


def test_verification_link_points_at_a_route_that_exists(monkeypatch):
    body = _captured_link(
        lambda: notifications.send_verification_email(email="a@example.com", token="t"),
        monkeypatch,
    )
    assert "https://app.example.com/verify-email?token=t" in body
    assert "/verify-email" in _frontend_routes()


def test_reset_link_points_at_a_route_that_exists(monkeypatch):
    body = _captured_link(
        lambda: notifications.send_password_reset_email(email="a@example.com", token="t"),
        monkeypatch,
    )
    assert "https://app.example.com/reset-password?token=t" in body
    assert "/reset-password" in _frontend_routes()


def test_subscription_links_deep_link_into_an_existing_route(monkeypatch):
    """Billing lives in a panel on the app root, not at its own path.

    An earlier version of these emails pointed at /billing, which was never a
    route -- every renewal reminder would have landed on a 404.
    """
    expiring = _captured_link(
        lambda: notifications.send_subscription_expiring_email(
            email="a@example.com", plan="pro", days_left=3
        ),
        monkeypatch,
    )
    downgraded = _captured_link(
        lambda: notifications.send_subscription_downgraded_email(email="a@example.com", plan="pro"),
        monkeypatch,
    )

    for body in (expiring, downgraded):
        assert "https://app.example.com/?panel=billing" in body
        assert "/billing?" not in body
    assert "/" in _frontend_routes()
