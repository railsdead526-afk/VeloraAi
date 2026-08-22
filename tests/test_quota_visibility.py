from datetime import UTC, datetime

from app.core.plans import get_plan_policy


def test_free_daily_quota_is_visible_configuration():
    policy = get_plan_policy("free")
    assert policy.daily_request_limit == 20


def test_admin_daily_quota_is_unlimited():
    policy = get_plan_policy("admin")
    assert policy.daily_request_limit is None


def test_daily_reset_is_utc_midnight():
    now = datetime(2026, 8, 21, 12, 30, tzinfo=UTC)
    reset = now.replace(hour=0, minute=0, second=0, microsecond=0)
    assert reset.hour == 0
    assert reset.tzinfo == UTC
