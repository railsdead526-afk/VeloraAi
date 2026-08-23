# ADR 0004: Provider-agnostic payments

Status: Accepted
Date: 2026-08-22

## Context

Midtrans was wired directly into `app/api/v1/payments.py` and into
`app/services/billing_service.py`. The consequence was subtler than "we can
only use one gateway": Midtrans's status vocabulary *was* the subscription
logic's vocabulary.

```python
PAID_STATUSES = {"settlement", "capture"}
FAILED_STATUSES = {"deny", "cancel", "expire", "failure"}
```

Those sets lived in `billing_service`. The definition of "this customer has
paid" was a string comparison against one vendor's wording, in the module that
grants entitlement.

Two forces made this urgent rather than theoretical:

1. Distribution. An Android build on Google Play must use Google Play Billing
   for in-app digital purchases; User Choice Billing exists in Indonesia but
   requires a registered business, which VeloraAi does not yet have. Web and
   Android will therefore very likely run **two payment systems at once**, not
   one after the other.
2. The gateway choice itself is unsettled.

## Decision

A provider implements `PaymentProvider` (`app/services/payments/base.py`) and
is responsible for its own credentials, its own signature scheme, and mapping
its own status strings to a canonical `PaymentOutcome`.

`PaymentOutcome` is `PENDING`, `PAID`, `FAILED`, `REFUNDED`, `UNKNOWN`.
Everything above the adapter reasons about outcomes; only the adapter knows
what "settlement" means.

Three details that carry real weight:

**`UNKNOWN` is distinct from `FAILED`.** An unrecognised status — a new state a
gateway introduces, or a fraud review — must not revoke or deny a paying
customer. Collapsing it into `FAILED` would make an unknown unknown cost
somebody their plan. There is a test for exactly this.

**`authorize` maps to `PENDING`, not `PAID`.** Funds are reserved, not
captured. Treating an authorisation as payment grants a plan for money that may
never arrive.

**The raw provider status is still persisted.** `Payment.status` keeps the
gateway's own wording so support and reconciliation can see what actually
happened; only the branching uses the canonical outcome. This also meant no
data migration.

`supports_refund` is a capability flag rather than an assumption, because
app-store providers settle refunds out of band and the API should say so
plainly instead of failing a call.

## Consequences

Adding Xendit, Duitku, or Google Play Billing means writing one adapter and
registering it. Nothing in the subscription lifecycle changes.

`tests/test_payment_providers.py` proves the claim rather than asserting it: it
registers a fake gateway with a different notification shape, no widget token,
and its own status words, then drives the real endpoints through it.

The refactor also exposed a coupling in the test suite itself. Several tests
patched `app.api.v1.payments.MidtransService` — reaching through the API module
to stub a gateway. They now patch the gateway class directly, which is the
seam that actually exists.

Cost: one more indirection between the endpoint and the HTTP call, and a
provider author must map statuses correctly. The mapping is small, explicit,
and directly tested, which is a better place for that risk than spread across
the billing logic.
