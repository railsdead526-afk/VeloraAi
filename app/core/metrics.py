"""Prometheus metrics.

Kept in one module so the rest of the codebase records business and technical
signals through named helpers rather than reaching for the client library.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

REGISTRY = CollectorRegistry(auto_describe=True)

http_requests_total = Counter(
    "velora_http_requests_total",
    "HTTP requests handled.",
    ["method", "path", "status"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "velora_http_request_duration_seconds",
    "HTTP request latency.",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    registry=REGISTRY,
)

ai_requests_total = Counter(
    "velora_ai_requests_total",
    "AI provider calls.",
    ["provider", "model", "outcome"],
    registry=REGISTRY,
)

ai_tokens_total = Counter(
    "velora_ai_tokens_total",
    "AI tokens consumed, split by direction.",
    ["provider", "model", "direction"],
    registry=REGISTRY,
)

tool_executions_total = Counter(
    "velora_tool_executions_total",
    "Tool executions.",
    ["tool", "outcome"],
    registry=REGISTRY,
)

auth_events_total = Counter(
    "velora_auth_events_total",
    "Authentication events.",
    ["event", "outcome"],
    registry=REGISTRY,
)

payment_events_total = Counter(
    "velora_payment_events_total",
    "Payment lifecycle events.",
    ["provider", "status"],
    registry=REGISTRY,
)

subscription_state = Gauge(
    "velora_subscriptions",
    "Subscriptions by plan and status, refreshed by the maintenance job.",
    ["plan", "status"],
    registry=REGISTRY,
)

quota_rejections_total = Counter(
    "velora_quota_rejections_total",
    "Requests refused because a plan quota was exhausted.",
    ["plan"],
    registry=REGISTRY,
)


def normalize_path(path: str) -> str:
    """Collapse identifiers so cardinality stays bounded.

    ``/api/v1/conversations/42/messages`` becomes
    ``/api/v1/conversations/{id}/messages``.
    """
    parts = []
    for segment in path.split("/"):
        parts.append("{id}" if segment.isdigit() else segment)
    return "/".join(parts) or "/"


def render() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
