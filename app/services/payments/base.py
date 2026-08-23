"""Provider-agnostic payment contract.

Before this existed, Midtrans was wired directly into the API layer and into
`billing_service`, so its status vocabulary ("settlement", "deny", "capture")
was the subscription logic's vocabulary too. Swapping gateways, or supporting
two at once — a web gateway plus Google Play Billing on Android — meant
rewriting both.

A provider now translates its own vocabulary into a canonical `PaymentOutcome`
at the boundary. Everything upstream of that boundary reasons about outcomes,
never about a particular gateway's strings.

The raw provider status is still carried alongside and persisted, because
support and reconciliation need to see exactly what the gateway said.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class PaymentProviderError(RuntimeError):
    """Raised when a provider cannot be reached or returns something unusable."""


class PaymentOutcome(StrEnum):
    """What a payment means to the business, independent of gateway wording."""

    #: Created, awaiting the customer.
    PENDING = "pending"
    #: Money captured. This is the only outcome that grants entitlement.
    PAID = "paid"
    #: Declined, cancelled, or expired. Terminal, but the user may retry.
    FAILED = "failed"
    #: Money returned. Terminal, and revokes entitlement.
    REFUNDED = "refunded"
    #: Recognised transaction in a state we do not act on, such as a fraud
    #: review. Deliberately distinct from FAILED so an ambiguous state is never
    #: silently treated as a decline.
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CheckoutSession:
    """Everything the client needs to start paying."""

    order_id: str
    #: Opaque handle for an embedded widget, when the provider offers one.
    token: str | None
    #: Hosted page to redirect to.
    redirect_url: str
    amount: int
    currency: str


@dataclass(frozen=True)
class TransactionStatus:
    """A provider's answer to "what happened to this order?"."""

    order_id: str
    outcome: PaymentOutcome
    #: Exactly what the provider called it. Persisted for reconciliation.
    raw_status: str
    #: String, not int: providers format amounts inconsistently
    #: ("99000" vs "99000.00") and comparison must be done on their own terms.
    gross_amount: str
    transaction_id: str | None = None
    payment_type: str | None = None


@dataclass(frozen=True)
class RefundResult:
    outcome: PaymentOutcome
    raw_status: str
    amount: int
    reference: str | None = None


@dataclass(frozen=True)
class NotificationEnvelope:
    """A webhook body after the provider has authenticated it.

    `signature_valid` is deliberately part of the parsed result rather than an
    exception: the caller must decide the response code, and must be able to
    audit a rejected notification.
    """

    order_id: str
    gross_amount: str | None
    signature_valid: bool
    raw_status: str | None = None


@runtime_checkable
class PaymentProvider(Protocol):
    """What every gateway must offer for the billing flow to work.

    A provider is responsible for its own credentials, its own signature
    scheme, and mapping its own status strings to `PaymentOutcome`. It must not
    know anything about subscriptions, plans, or users.
    """

    #: Stored on Payment.provider and Subscription.provider.
    name: str
    #: False for providers where refunds are handled out of band, such as
    #: Google Play. The API surfaces a clear error instead of a failed call.
    supports_refund: bool

    def client_config(self) -> dict[str, Any]:
        """Non-secret settings the frontend needs. Must never leak a secret."""
        ...

    def create_checkout(
        self,
        *,
        order_id: str,
        amount: int,
        currency: str,
        customer_email: str,
        item_name: str,
    ) -> CheckoutSession: ...

    def parse_notification(self, payload: Mapping[str, Any]) -> NotificationEnvelope:
        """Authenticate a webhook body and extract the fields we act on."""
        ...

    def fetch_transaction(self, order_id: str) -> TransactionStatus:
        """Ask the provider directly. Never trust the webhook body alone."""
        ...

    def refund(self, *, order_id: str, amount: int, reason: str) -> RefundResult: ...
