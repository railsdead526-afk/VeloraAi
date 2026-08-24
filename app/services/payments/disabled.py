"""A provider for deployments that do not sell anything yet.

Running with payments half-configured is the dangerous state: prices default to
zero, credentials are blank, and a checkout either crashes or silently grants a
plan for free. Making "no payments" an explicit, first-class provider means the
system fails loudly and predictably instead.

Set `PAYMENT_PROVIDER=disabled` to use it. Production validation then skips the
gateway and pricing requirements, because there is nothing to sell.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.payments.base import (
    CheckoutSession,
    NotificationEnvelope,
    PaymentProviderError,
    RefundResult,
    TransactionStatus,
)

_MESSAGE = (
    "Payments are not enabled on this deployment. "
    "Set PAYMENT_PROVIDER to a configured gateway to accept upgrades."
)


class DisabledProvider:
    name = "disabled"
    supports_refund = False

    def client_config(self) -> dict[str, Any]:
        # Answers rather than raises, so the UI can render an honest
        # "upgrades unavailable" state instead of an error.
        return {"provider": self.name, "enabled": False, "reason": _MESSAGE}

    def create_checkout(
        self, *, order_id: str, amount: int, currency: str, customer_email: str, item_name: str
    ) -> CheckoutSession:
        raise PaymentProviderError(_MESSAGE)

    def parse_notification(self, payload: Mapping[str, Any]) -> NotificationEnvelope:
        raise PaymentProviderError(_MESSAGE)

    def fetch_transaction(self, order_id: str) -> TransactionStatus:
        raise PaymentProviderError(_MESSAGE)

    def refund(self, *, order_id: str, amount: int, reason: str) -> RefundResult:
        raise PaymentProviderError(_MESSAGE)
