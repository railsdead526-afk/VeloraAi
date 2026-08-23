"""Resolution of the configured payment provider."""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import settings
from app.services.payments.base import PaymentProvider, PaymentProviderError
from app.services.payments.midtrans import MidtransProvider

#: Constructors rather than instances: a provider reads credentials from
#: settings at build time, and tests patch settings between cases.
_FACTORIES: dict[str, Callable[[], PaymentProvider]] = {
    "midtrans": MidtransProvider,
}


def available_providers() -> tuple[str, ...]:
    return tuple(sorted(_FACTORIES))


def register_provider(name: str, factory: Callable[[], PaymentProvider]) -> None:
    """Add a provider. Used by tests and by future gateway integrations."""
    _FACTORIES[name.strip().lower()] = factory


def get_provider(name: str | None = None) -> PaymentProvider:
    key = (name or settings.payment_provider).strip().lower()
    factory = _FACTORIES.get(key)
    if factory is None:
        raise PaymentProviderError(
            f"Unknown payment provider {key!r}; configured providers: "
            f"{', '.join(available_providers())}"
        )
    return factory()
