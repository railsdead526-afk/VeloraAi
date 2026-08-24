"""Invoice numbers must stay unique under concurrent settlements.

`invoice_number` carries a UNIQUE constraint and is derived from the current
maximum for the month. Two provider notifications settling at the same moment
both read the same high-water mark, so the second commit died with an
IntegrityError - failing a webhook for money that had genuinely been received.
Midtrans retries, so the payment usually lands eventually, but there is a window
where the customer has paid and has no plan.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.billing import Payment
from app.models.user import User
from app.services import billing_service
from app.services.billing_service import (
    assign_invoice_number,
    next_invoice_number,
    tax_component,
)


@pytest.fixture
def user(db):
    account = User(email="invoice@example.com", hashed_password="hash", role="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def _payment(db, user, order_id: str) -> Payment:
    payment = Payment(
        user_id=user.id,
        provider="midtrans",
        provider_order_id=order_id,
        amount=100_000,
        tax_amount=0,
        currency="IDR",
        plan="pro",
        status="pending",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def test_numbers_increment_within_a_month(db, user):
    first = assign_invoice_number(db, _payment(db, user, "a"))
    db.commit()
    second = assign_invoice_number(db, _payment(db, user, "b"))
    db.commit()

    assert first.endswith("000001")
    assert second.endswith("000002")
    assert first[:12] == second[:12]


def test_assignment_retries_when_the_number_is_already_taken(db, user, monkeypatch):
    """The exact race, made deterministic.

    Two settlements read the counter before either commits, so both compute the
    same number. Simulated by forcing the first attempt to return a number that
    is already in the table.
    """
    taken = _payment(db, user, "taken-by-worker-a")
    taken.invoice_number = "INV-2026-08-000001"
    db.commit()

    real_next = billing_service.next_invoice_number
    calls = {"n": 0}

    def collide_once(session, *, now=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return "INV-2026-08-000001"
        return real_next(session, now=now)

    monkeypatch.setattr(billing_service, "next_invoice_number", collide_once)

    second = _payment(db, user, "worker-b")
    assigned = billing_service.assign_invoice_number(
        db, second, now=datetime(2026, 8, 1, tzinfo=UTC)
    )
    db.commit()

    assert calls["n"] >= 2, "the collision was never retried"
    assert assigned == "INV-2026-08-000002"
    assert db.get(Payment, second.id).invoice_number == assigned


def test_assignment_gives_up_after_repeated_collisions(db, user, monkeypatch):
    taken = _payment(db, user, "blocker")
    taken.invoice_number = "INV-2026-08-000001"
    db.commit()

    monkeypatch.setattr(
        billing_service, "next_invoice_number", lambda session, now=None: "INV-2026-08-000001"
    )

    payment = _payment(db, user, "doomed")
    with pytest.raises(RuntimeError, match="unique invoice number"):
        billing_service.assign_invoice_number(db, payment)


def test_assignment_survives_a_taken_number(db, user):
    taken = _payment(db, user, "taken")
    taken.invoice_number = next_invoice_number(db)
    db.commit()

    later = _payment(db, user, "later")
    assigned = assign_invoice_number(db, later)
    db.commit()

    assert assigned.endswith("000002")


def test_every_number_in_a_batch_is_unique(db, user):
    numbers = set()
    for index in range(12):
        payment = _payment(db, user, f"batch-{index}")
        numbers.add(assign_invoice_number(db, payment))
        db.commit()

    assert len(numbers) == 12


def test_a_direct_duplicate_is_still_rejected_by_the_database(db, user):
    """The constraint must remain the backstop, not just the retry loop."""
    first = _payment(db, user, "dup-a")
    first.invoice_number = "INV-2026-08-000999"
    db.commit()

    second = _payment(db, user, "dup-b")
    second.invoice_number = "INV-2026-08-000999"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_numbering_restarts_each_month(db, user):
    january = datetime(2026, 1, 5, tzinfo=UTC)
    february = datetime(2026, 2, 5, tzinfo=UTC)

    first = assign_invoice_number(db, _payment(db, user, "jan"), now=january)
    db.commit()
    second = assign_invoice_number(db, _payment(db, user, "feb"), now=february)
    db.commit()

    assert first == "INV-2026-01-000001"
    assert second == "INV-2026-02-000001"


def test_tax_component_is_extracted_from_a_gross_amount(db, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "vat_percent", 11)
    # 111_000 gross at 11% inclusive VAT is 11_000 tax on 100_000 net.
    assert tax_component(111_000) == 11_000

    monkeypatch.setattr(settings, "vat_percent", 0)
    assert tax_component(111_000) == 0
