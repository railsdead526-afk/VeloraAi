# ADR 0003: Subscription periods, grace, and expiry

Status: Accepted
Date: 2026-08-22

## Context

`apply_payment_notification` created `Subscription(status="active")` and never
populated `current_period_start` or `current_period_end`, even though both
columns existed. No scheduler existed anywhere in the repository.

The commercial consequence: a user paid once and held a paid plan permanently.
There was no second invoice, no downgrade, and no way to detect the loss. The
subscription business model had no implementation.

## Decision

1. Settlement writes a bounded period: `current_period_end = anchor + SUBSCRIPTION_PERIOD_DAYS`,
   plus `grace_until = current_period_end + SUBSCRIPTION_GRACE_DAYS`.
2. Renewals extend from `max(now, current_period_end)`, so paying early adds a
   period instead of forfeiting unused days.
3. Repeat purchases reuse the existing subscription row for that plan rather
   than creating duplicates.
4. `sweep_subscriptions()` runs hourly from `scripts/run_maintenance.py`:
   - period lapsed, still inside grace → `past_due` (entitlement retained),
   - grace elapsed → `expired` or `canceled`, and the user is downgraded,
   - renewal reminders at 7, 3, and 1 days out.
5. Entitlement is computed in `sync_user_role` from subscriptions whose grace
   window is still open, so `past_due` users keep access exactly as long as the
   grace policy says.
6. Legacy rows with no recorded period are backfilled with a period rather than
   treated as perpetual.

`admin` is never downgraded by the sweep.

## Consequences

The sweep is idempotent, so duplicate or retried runs are harmless. The job
becoming a single point of revenue failure is the main new risk, so it is
alerted on if it has not succeeded within three hours (`docs/runbook.md` §8).

Payments remain one-off charges initiated by the user. Card-on-file recurring
billing through Midtrans tokenisation is the next step; the period model above
is a prerequisite for it.
