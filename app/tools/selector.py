from __future__ import annotations

import re
from typing import Iterable

from app.tools.base import ToolDefinition


_PLATFORM_KEYWORDS = {
    "github": {"github", "repo", "repository", "branch", "pull request", "pr", "issue", "commit"},
    "vercel": {"vercel", "deployment", "deploy", "domain"},
    "railway": {"railway", "service", "deployment", "deploy"},
    "cloudflare": {"cloudflare", "dns", "worker", "workers", "r2", "zone"},
    "supabase": {"supabase", "postgres", "database", "sql", "edge function"},
    "terminal": {"terminal", "shell", "command", "bash", "npm", "pip", "build", "test", "lint"},
    "calculator": {"calculate", "calculator", "hitung", "berapa", "math"},
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_+-]+", text.lower()))


def select_tools(
    tools: Iterable[ToolDefinition],
    user_text: str,
    *,
    plan: str,
    max_tools: int = 12,
) -> list[ToolDefinition]:
    """Select a small contextual subset of registered tools for the model."""
    if max_tools < 1:
        return []

    normalized_plan = plan.lower()
    available = [tool for tool in tools if tool.allows_plan(normalized_plan)]
    normalized = user_text.lower()
    tokens = _tokens(user_text)
    scored: list[tuple[int, int, ToolDefinition]] = []

    for index, tool in enumerate(available):
        name_parts = set(tool.name.lower().replace("-", "_").split("_"))
        score = len(tokens & name_parts) * 3

        for platform, keywords in _PLATFORM_KEYWORDS.items():
            if platform in tool.name.lower() and any(
                keyword in normalized or keyword in tokens for keyword in keywords
            ):
                score += 8
                break

        if tool.name.lower() in normalized:
            score += 20

        if score > 0:
            scored.append((score, -index, tool))

    if not scored:
        scored = [(0, -index, tool) for index, tool in enumerate(available)]

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [tool for _, _, tool in scored[:max_tools]]
