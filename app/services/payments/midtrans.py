"""Midtrans implementation of the payment provider contract.

All Midtrans-specific vocabulary lives here and nowhere else.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.config import settings
from app.services.midtrans_service import MidtransError, MidtransService
from app.services.payments.base import (
    CheckoutSession,
    NotificationEnvelope,
    PaymentOutcome,
    PaymentProviderError,
    RefundResult,
    TransactionStatus,
    validate_redirect_url,
)

#: Midtrans status vocabulary, mapped to what it means for entitlement.
#: `capture` is a card authorisation that has been captured, so it is money in.
#: `authorize` deliberately is not: the funds are only reserved.
_OUTCOMES: dict[str, PaymentOutcome] = {
    "settlement": PaymentOutcome.PAID,
    "capture": PaymentOutcome.PAID,
    "pending": PaymentOutcome.PENDING,
    "authorize": PaymentOutcome.PENDING,
    "deny": PaymentOutcome.FAILED,
    "cancel": PaymentOutcome.FAILED,
    "expire": PaymentOutcome.FAILED,
    "failure": PaymentOutcome.FAILED,
    "refund": PaymentOutcome.REFUNDED,
    "partial_refund": PaymentOutcome.REFUNDED,
    "chargeback": PaymentOutcome.REFUNDED,
    "partial_chargeback": PaymentOutcome.REFUNDED,
}


def classify(raw_status: str) -> PaymentOutcome:
    """Map a Midtrans status to a canonical outcome.

    An unrecognised status becomes UNKNOWN rather than FAILED: a new status we
    have not seen must not silently revoke or deny a paying customer.
    """
    return _OUTCOMES.get((raw_status or "").strip().lower(), PaymentOutcome.UNKNOWN)


class MidtransProvider:
    name = "midtrans"
    supports_refund = True

    def _service(self) -> MidtransService:
        try:
            return MidtransService()
        except MidtransError as exc:
            raise PaymentProviderError(str(exc)) from exc

    def client_config(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "is_production": settings.midtrans_is_production,
            "pro_price_idr": settings.pro_price_idr,
            "max_price_idr": settings.max_price_idr,
        }

    def create_checkout(
        self,
        *,
        order_id: str,
        amount: int,
        currency: str,
        customer_email: str,
        item_name: str,
    ) -> CheckoutSession:
        if currency != "IDR":
            raise PaymentProviderError("Midtrans only settles in IDR")
        try:
            result = self._service().create_snap_transaction(
                order_id=order_id,
                gross_amount=amount,
                customer_email=customer_email,
                item_name=item_name,
            )
        except MidtransError as exc:
            raise PaymentProviderError(str(exc)) from exc

        return CheckoutSession(
            order_id=order_id,
            token=result.get("token"),
            redirect_url=validate_redirect_url(result.get("redirect_url", "")),
            amount=amount,
            currency=currency,
        )

    def parse_notification(self, payload: Mapping[str, Any]) -> NotificationEnvelope:
        order_id = str(payload.get("order_id", "")).strip()
        status_code = str(payload.get("status_code", "")).strip()
        gross_amount = str(payload.get("gross_amount", "")).strip()
        signature_key = str(payload.get("signature_key", "")).strip()

        if not order_id or not status_code or not gross_amount or not signature_key:
            raise PaymentProviderError("Invalid notification payload")

        valid = self._service().verify_notification_signature(
            order_id=order_id,
            status_code=status_code,
            gross_amount=gross_amount,
            signature_key=signature_key,
        )
        return NotificationEnvelope(
            order_id=order_id,
            gross_amount=gross_amount,
            signature_valid=valid,
            raw_status=str(payload.get("transaction_status", "")).strip() or None,
        )

    def fetch_transaction(self, order_id: str) -> TransactionStatus:
        try:
            data = self._service().get_transaction_status(order_id)
        except MidtransError as exc:
            raise PaymentProviderError(str(exc)) from exc

        raw_status = str(data.get("transaction_status", "")).strip()
        return TransactionStatus(
            order_id=str(data.get("order_id", "")),
            outcome=classify(raw_status),
            raw_status=raw_status,
            gross_amount=str(data.get("gross_amount", "")),
            transaction_id=data.get("transaction_id"),
            payment_type=data.get("payment_type"),
        )

    def refund(self, *, order_id: str, amount: int, reason: str) -> RefundResult:
        try:
            result = self._service().refund_transaction(order_id, amount, reason)
        except MidtransError as exc:
            raise PaymentProviderError(str(exc)) from exc

        raw_status = str(result.get("status_code", result.get("status", "pending")))
        # Midtrans answers refunds with an HTTP-style status code, where 200
        # means the refund settled immediately.
        settled = raw_status in {"200", "settlement"}
        return RefundResult(
            outcome=PaymentOutcome.REFUNDED if settled else PaymentOutcome.PENDING,
            raw_status=raw_status,
            amount=amount,
            reference=result.get("refund_key") or result.get("transaction_id"),
        )
