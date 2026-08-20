"""Compatibility wrapper for the canonical AI tool loop.

The active agent implementation lives in ``app.services.ai_tool_loop``.
This module is kept temporarily so older callers do not get a breaking import,
while ensuring there is only one tool-execution implementation.
"""

from __future__ import annotations

from typing import Any

from app.services import ai_tool_loop
from app.tools.registry import ToolRegistry


def generate_with_tools(
    messages: list[dict[str, Any]],
    *,
    registry: ToolRegistry,
    plan: str,
    confirmed: bool = False,
) -> str:
    """Generate a final response through the canonical agent loop."""
    result = ai_tool_loop.generate_ai_reply_with_tools(
        messages,
        plan=plan,
        confirmed=confirmed,
        registry=registry,
    )
    return result.content
