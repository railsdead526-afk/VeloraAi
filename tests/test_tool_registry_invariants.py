"""Structural invariants every registered tool must satisfy.

The registry is a 55-entry declarative table. Reviewing it by eye does not scale
and does not survive the next tool being added, so the rules are asserted here
instead: an unconstrained schema, a missing plan restriction or a destructive
tool that skips confirmation fails the build.
"""

from __future__ import annotations

import pytest

from app.tools.base import ToolRisk
from app.tools.bootstrap import get_registry
from app.tools.policy import policy


@pytest.fixture(scope="module")
def tools():
    registry = get_registry()
    definitions = registry.list()
    assert definitions, "the registry must not be empty"
    return definitions


def test_tool_names_are_unique(tools):
    names = [tool.name for tool in tools]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("field", ["type", "additionalProperties"])
def test_schemas_are_closed_objects(tools, field):
    expected = {"type": "object", "additionalProperties": False}[field]
    offenders = [tool.name for tool in tools if (tool.parameters or {}).get(field) != expected]
    assert offenders == [], f"tools with an unexpected schema {field}: {offenders}"


def test_required_properties_are_declared(tools):
    offenders = []
    for tool in tools:
        schema = tool.parameters or {}
        declared = set((schema.get("properties") or {}).keys())
        required = set(schema.get("required") or [])
        if not required <= declared:
            offenders.append((tool.name, sorted(required - declared)))
    assert offenders == []


def test_every_tool_is_described(tools):
    assert [tool.name for tool in tools if not (tool.description or "").strip()] == []


def test_execution_budgets_are_sane(tools):
    offenders = [
        tool.name
        for tool in tools
        if not (0 < tool.timeout_seconds <= 120) or tool.max_calls_per_request < 1
    ]
    assert offenders == []


def test_free_plan_only_gets_low_risk_tools(tools):
    offenders = [
        f"{tool.name} ({tool.risk_level})"
        for tool in tools
        if "free" in tool.allowed_plans and tool.risk_level is not ToolRisk.LOW
    ]
    assert offenders == [], f"free plan must not reach risky tools: {offenders}"


def test_destructive_tools_require_confirmation(tools):
    offenders = [
        tool.name
        for tool in tools
        if tool.risk_level in {ToolRisk.DESTRUCTIVE, ToolRisk.PRIVILEGED}
        and not policy.requires_approval(tool)
    ]
    assert offenders == []


def test_low_risk_tools_do_not_ask_for_confirmation(tools):
    """Confirmation prompts are a scarce resource; spending them on reads trains
    users to click through the ones that matter."""
    offenders = [
        tool.name
        for tool in tools
        if tool.risk_level is ToolRisk.LOW and tool.requires_confirmation
    ]
    assert offenders == []
