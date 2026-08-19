import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.ai_service import AIResult, _build_api_messages, _parse_usage, _provider_config
from app.tools.executor import ToolExecutionError, execute_tool
from app.tools.registry import ToolRegistry
from app.tools.selector import select_tools

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
MAX_TOOLS_PER_REQUEST = 12


def _tool_message(tool_call_id: str, result: Any) -> dict[str, str]:
    try:
        content = json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        content = str(result)
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    arguments = json.loads(raw_arguments) if isinstance(raw_arguments, str) else raw_arguments
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    return arguments


def _selected_tools(registry: ToolRegistry, messages: list[dict], plan: str):
    return select_tools(
        registry.list(),
        messages[-1].get("content", "") if messages else "",
        plan=plan,
        max_tools=MAX_TOOLS_PER_REQUEST,
    )


def _run_tool(
    registry: ToolRegistry,
    *,
    name: str,
    arguments: dict[str, Any],
    plan: str,
    confirmed: bool,
    call_counts: dict[str, int],
) -> Any:
    return asyncio.run(
        execute_tool(
            registry,
            name=name,
            arguments=arguments,
            plan=plan,
            confirmed=confirmed,
            call_counts=call_counts,
        )
    )


def generate_ai_reply_with_tools(
    messages: list[dict],
    *,
    plan: str,
    confirmed: bool = False,
    registry: ToolRegistry,
) -> AIResult:
    if settings.ai_provider == "mock":
        from app.services.ai_service import _mock_result
        return _mock_result(messages)

    if settings.ai_provider not in {"openai", "llama"}:
        raise RuntimeError("AI provider is not configured")

    api_key, base_url, model, provider = _provider_config()
    if provider == "openai" and not api_key:
        raise RuntimeError("AI provider belum dikonfigurasi")

    api_messages = _build_api_messages(messages)
    selected_tools = _selected_tools(registry, messages, plan)
    selected_names = {tool.name for tool in selected_tools}
    total_input_tokens = 0
    total_output_tokens = 0
    usage_seen = False
    call_counts: dict[str, int] = {}

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for _round in range(MAX_TOOL_ROUNDS):
        payload: dict[str, Any] = {
            "model": model,
            "messages": api_messages,
            "temperature": 0.7,
            "tools": registry.schemas_for(selected_tools),
            "tool_choice": "auto",
        }
        try:
            with httpx.Client(timeout=httpx.Timeout(settings.ai_timeout_seconds)) as client:
                response = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.exception("AI tool-loop request failed")
            raise RuntimeError("AI service temporarily unavailable") from exc

        input_tokens, output_tokens = _parse_usage(data)
        if input_tokens is not None and output_tokens is not None:
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            usage_seen = True

        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("AI provider returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            if not content:
                raise RuntimeError("AI provider returned an empty response")
            return AIResult(
                content=content.strip(),
                input_tokens=total_input_tokens if usage_seen else None,
                output_tokens=total_output_tokens if usage_seen else None,
                model=model,
            )

        api_messages.append(message)
        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = function.get("name")
            raw_arguments = function.get("arguments") or "{}"
            tool_call_id = tool_call.get("id")
            if not name or not tool_call_id:
                raise RuntimeError("AI provider returned an invalid tool call")
            if name not in selected_names:
                result = {"error": "Tool is not available in the current tool context"}
                api_messages.append(_tool_message(tool_call_id, result))
                continue
            try:
                arguments = _parse_tool_arguments(raw_arguments)
                result = _run_tool(
                    registry,
                    name=name,
                    arguments=arguments,
                    plan=plan,
                    confirmed=confirmed,
                    call_counts=call_counts,
                )
            except (ToolExecutionError, ValueError, json.JSONDecodeError) as exc:
                result = {"error": str(exc)}
            api_messages.append(_tool_message(tool_call_id, result))

    raise RuntimeError("AI tool execution exceeded the maximum number of rounds")


async def generate_ai_reply_with_tools_async(
    messages: list[dict],
    *,
    plan: str,
    confirmed: bool = False,
    registry: ToolRegistry,
) -> AIResult:
    if settings.ai_provider == "mock":
        from app.services.ai_service import _mock_result
        return _mock_result(messages)
    if settings.ai_provider not in {"openai", "llama"}:
        raise RuntimeError("AI provider is not configured")

    api_key, base_url, model, provider = _provider_config()
    if provider == "openai" and not api_key:
        raise RuntimeError("AI provider belum dikonfigurasi")

    api_messages = _build_api_messages(messages)
    selected_tools = _selected_tools(registry, messages, plan)
    selected_names = {tool.name for tool in selected_tools}
    total_input_tokens = 0
    total_output_tokens = 0
    usage_seen = False
    call_counts: dict[str, int] = {}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.ai_timeout_seconds)) as client:
        for _round in range(MAX_TOOL_ROUNDS):
            payload: dict[str, Any] = {
                "model": model,
                "messages": api_messages,
                "temperature": 0.7,
                "tools": registry.schemas_for(selected_tools),
                "tool_choice": "auto",
            }
            try:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                logger.exception("Async AI tool-loop request failed")
                raise RuntimeError("AI service temporarily unavailable") from exc

            input_tokens, output_tokens = _parse_usage(data)
            if input_tokens is not None and output_tokens is not None:
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                usage_seen = True

            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("AI provider returned no choices")
            message = choices[0].get("message") or {}
            content = message.get("content")
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                if not content:
                    raise RuntimeError("AI provider returned an empty response")
                return AIResult(
                    content=content.strip(),
                    input_tokens=total_input_tokens if usage_seen else None,
                    output_tokens=total_output_tokens if usage_seen else None,
                    model=model,
                )

            api_messages.append(message)
            for tool_call in tool_calls:
                function = tool_call.get("function") or {}
                name = function.get("name")
                raw_arguments = function.get("arguments") or "{}"
                tool_call_id = tool_call.get("id")
                if not name or not tool_call_id:
                    raise RuntimeError("AI provider returned an invalid tool call")
                if name not in selected_names:
                    result = {"error": "Tool is not available in the current tool context"}
                else:
                    try:
                        arguments = _parse_tool_arguments(raw_arguments)
                        result = await execute_tool(
                            registry,
                            name=name,
                            arguments=arguments,
                            plan=plan,
                            confirmed=confirmed,
                            call_counts=call_counts,
                        )
                    except (ToolExecutionError, ValueError, json.JSONDecodeError) as exc:
                        result = {"error": str(exc)}
                api_messages.append(_tool_message(tool_call_id, result))

    raise RuntimeError("AI tool execution exceeded the maximum number of rounds")
