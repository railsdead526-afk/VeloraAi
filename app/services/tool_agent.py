import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.tools.executor import ToolExecutionError, execute_tool
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4


def _provider() -> tuple[str, str, str]:
    if settings.ai_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("AI provider belum dikonfigurasi")
        return settings.openai_base_url, settings.openai_api_key, settings.openai_model
    if settings.ai_provider == "llama":
        return settings.llama_base_url, settings.llama_api_key, settings.llama_model
    raise RuntimeError("Tool calling requires an OpenAI-compatible AI provider")


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def generate_with_tools(
    messages: list[dict[str, Any]],
    *,
    registry: ToolRegistry,
    plan: str,
    confirmed: bool = False,
) -> str:
    base_url, api_key, model = _provider()
    conversation = list(messages)
    tools = registry.schemas()

    for _ in range(MAX_TOOL_ROUNDS):
        payload = {
            "model": model,
            "messages": conversation,
            "tools": tools,
            "tool_choice": "auto",
        }
        try:
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers=_headers(api_key),
                json=payload,
                timeout=httpx.Timeout(settings.ai_timeout_seconds),
            )
            response.raise_for_status()
            data = response.json()
            message = (data.get("choices") or [{}])[0].get("message") or {}
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            logger.exception("Tool-capable AI request failed")
            raise RuntimeError("AI service temporarily unavailable") from exc

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            content = message.get("content")
            if not content:
                raise RuntimeError("AI provider returned an empty response")
            return content.strip()

        conversation.append({
            "role": "assistant",
            "content": message.get("content"),
            "tool_calls": tool_calls,
        })

        for call in tool_calls:
            function = call.get("function") or {}
            name = function.get("name")
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be an object")
                result = _run_tool_sync(registry, name, arguments, plan, confirmed)
            except (ValueError, TypeError, json.JSONDecodeError, ToolExecutionError, KeyError) as exc:
                result = {"error": str(exc)}

            conversation.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "name": name,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            })

    raise RuntimeError("Tool calling exceeded the maximum number of rounds")


def _run_tool_sync(
    registry: ToolRegistry,
    name: str | None,
    arguments: dict[str, Any],
    plan: str,
    confirmed: bool,
) -> Any:
    if not name:
        raise ToolExecutionError("Tool name is required")
    import asyncio
    return asyncio.run(execute_tool(registry, name=name, arguments=arguments, plan=plan, confirmed=confirmed))
