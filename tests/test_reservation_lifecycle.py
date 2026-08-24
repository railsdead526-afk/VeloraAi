"""Reservation lifecycle around long-running streams.

A reservation stops one account over-committing while a request is in flight.
It is short-lived bookkeeping, not an audit record, so the failure modes that
matter are the ones that punish the user for a slow request.

The original code raised RuntimeError when completing a reservation that was no
longer `reserved`. That happens routinely: an agent turn with several tool
rounds can outlive the TTL, and the next request from the same account sweeps
the expired row to `released`. The raise then aborted the caller's transaction
in agent_stream - the reply had already been streamed to the user's screen, but
the messages were rolled back and the usage never recorded. The user lost the
answer and we paid a provider bill we could not charge for.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.plans import get_plan_policy
from app.models.ai_request_reservation import AIRequestReservation
from app.models.user import User
from app.services import quota_service


@pytest.fixture
def user(db):
    account = User(email="reservation@example.com", hashed_password="hash", role="free")
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@pytest.fixture
def policy():
    return get_plan_policy("free")


def _expire(db, reservation_id: int) -> AIRequestReservation:
    reservation = db.get(AIRequestReservation, reservation_id)
    reservation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    return reservation


def test_reservation_ttl_outlasts_a_full_agent_turn():
    """Four tool rounds at a 45s provider timeout plus 65s tools is ~7.5 minutes."""
    assert timedelta(minutes=20) <= quota_service.RESERVATION_TTL


def test_completing_a_swept_reservation_succeeds(db, user, policy):
    first = quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    assert first is not None

    _expire(db, first)
    # A second request from the same account sweeps expired reservations.
    quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    assert db.get(AIRequestReservation, first).status == "released"

    # Must not raise: the work behind the reservation did finish.
    quota_service.complete_request_reservation(db, first)
    db.commit()

    settled = db.get(AIRequestReservation, first)
    assert settled.status == "completed"
    assert settled.completed_at is not None
    assert settled.released_at is None


def test_completion_is_idempotent(db, user, policy):
    reservation_id = quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    quota_service.complete_request_reservation(db, reservation_id)
    db.commit()
    first_completed_at = db.get(AIRequestReservation, reservation_id).completed_at

    quota_service.complete_request_reservation(db, reservation_id)
    db.commit()

    settled = db.get(AIRequestReservation, reservation_id)
    assert settled.status == "completed"
    assert settled.completed_at == first_completed_at


def test_completing_a_missing_reservation_does_not_raise(db):
    quota_service.complete_request_reservation(db, 999_999)


def test_release_still_ignores_a_settled_reservation(db, user, policy):
    reservation_id = quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    quota_service.complete_request_reservation(db, reservation_id)
    db.commit()

    quota_service.release_request_reservation(db, reservation_id)
    db.commit()

    assert db.get(AIRequestReservation, reservation_id).status == "completed"


def test_expired_reservations_do_not_consume_quota(db, user, policy):
    """An abandoned request must not permanently cost the user a slot."""
    limit = policy.daily_request_limit
    assert limit is not None

    ids = []
    for _ in range(limit):
        ids.append(quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy))

    with pytest.raises(quota_service.QuotaExceededError):
        quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy)

    for reservation_id in ids:
        _expire(db, reservation_id)

    # Once they expire the slots come back.
    assert quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy) is not None


def test_purge_removes_only_old_settled_rows(db, user, policy):
    old_completed = quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy)
    quota_service.complete_request_reservation(db, old_completed)
    db.commit()
    aged = db.get(AIRequestReservation, old_completed)
    aged.created_at = datetime.now(UTC) - timedelta(days=30)
    db.commit()

    recent = quota_service.reserve_plan_request_quota(db, user_id=user.id, policy=policy)

    deleted = quota_service.purge_settled_reservations(db)

    assert deleted == 1
    assert db.get(AIRequestReservation, old_completed) is None
    # An in-flight reservation is never touched, however old.
    assert db.get(AIRequestReservation, recent) is not None
