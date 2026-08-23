from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.services.ai_provider import (
    auth_headers,
    build_api_messages,
    get_provider_config,
    parse_usage,
)
from app.services.ai_service import AIResult
from app.tools.base import ToolDefinition
from app.tools.executor import ToolExecutionError, execute_tool
from app.tools.registry import ToolRegistry
from app.tools.selector import select_tools

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
MAX_TOOLS_PER_REQUEST = 12
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 4.0
MAX_RETRY_AFTER_SECONDS = 10.0


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


def _selected_tools(
    registry: ToolRegistry, messages: list[dict], plan: str
) -> list[ToolDefinition]:
    return select_tools(
        registry.list(),
        messages[-1].get("content", "") if messages else "",
        plan=plan,
        max_tools=MAX_TOOLS_PER_REQUEST,
    )


def _is_retryable_http_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        return status_code in RETRYABLE_STATUS_CODES
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
            httpx.RemoteProtocolError,
        ),
    )


def _retry_delay(attempt: int, exc: Exception) -> float:
    """Exponential backoff, overridden by a sane ``Retry-After`` when the provider sends one."""
    if isinstance(exc, httpx.HTTPStatusError):
        raw = exc.response.headers.get("retry-after")
        if raw:
            try:
                retry_after = float(raw)
            except ValueError:
                retry_after = -1.0
            if 0 <= retry_after <= MAX_RETRY_AFTER_SECONDS:
                return retry_after
    return min(2.0**attempt, MAX_BACKOFF_SECONDS)


async def _backoff(attempt: int, exc: Exception) -> None:
    await asyncio.sleep(_retry_delay(attempt, exc))


async def _post_completion(
    client: httpx.AsyncClient, url: str, *, headers: dict[str, str], payload: dict[str, Any]
) -> dict[str, Any]:
    attempts = settings.ai_max_retries + 1
    for attempt in range(attempts):
        try:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except asyncio.CancelledError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            if attempt >= attempts - 1 or not _is_retryable_http_error(exc):
                raise
            logger.warning(
                "Retrying AI provider request",
                extra={"attempt": attempt + 1, "max_retries": settings.ai_max_retries},
            )
            await _backoff(attempt, exc)
            continue
        if not isinstance(data, dict):
            raise ValueError("AI provider returned a non-object response")
        return data
    raise RuntimeError("AI provider request failed")


def _completion_payload(
    *,
    model: str,
    api_messages: list[dict],
    registry: ToolRegistry,
    selected_tools: list[ToolDefinition],
    final_round: bool,
) -> dict[str, Any]:
    """Build the request body.

    On the final round the tools are withheld so the model is forced to produce a
    user-visible answer instead of yet another tool call. Without this the whole
    exchange used to end in a 500 and every token spent on it was wasted.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": api_messages,
        "temperature": 0.7,
    }
    if not final_round:
        payload["tools"] = registry.schemas_for(selected_tools)
        payload["tool_choice"] = "auto"
    return payload


async def generate_ai_reply_with_tools_async(
    messages: list[dict],
    *,
    plan: str,
    confirmed: bool = False,
    registry: ToolRegistry,
) -> AIResult:
    config = get_provider_config()
    if config.name == "mock":
        from app.services.ai_service import _mock_result

        return _mock_result(messages)
    if config.name not in {"openai", "llama"}:
        raise RuntimeError("AI provider is not configured")
    if config.name == "openai" and not config.api_key:
        raise RuntimeError("AI provider belum dikonfigurasi")

    api_messages = build_api_messages(messages)
    selected_tools = _selected_tools(registry, messages, plan)
    selected_names = {tool.name for tool in selected_tools}
    total_input_tokens = 0
    total_output_tokens = 0
    usage_seen = False
    call_counts: dict[str, int] = {}
    headers = auth_headers(config)

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.ai_timeout_seconds)) as client:
        for round_index in range(MAX_TOOL_ROUNDS):
            payload = _completion_payload(
                model=config.model,
                api_messages=api_messages,
                registry=registry,
                selected_tools=selected_tools,
                final_round=round_index == MAX_TOOL_ROUNDS - 1,
            )
            try:
                data = await _post_completion(
                    client,
                    f"{config.base_url}/chat/completions",
                    headers=headers,
                    payload=payload,
                )
            except asyncio.CancelledError:
                raise
            except (httpx.HTTPError, ValueError) as exc:
                logger.exception("AI tool-loop request failed")
                raise RuntimeError("AI service temporarily unavailable") from exc

            input_tokens, output_tokens = parse_usage(data)
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
                if not content or not content.strip():
                    raise RuntimeError("AI provider returned an empty response")
                return AIResult(
                    content=content.strip(),
                    input_tokens=total_input_tokens if usage_seen else None,
                    output_tokens=total_output_tokens if usage_seen else None,
                    model=config.model,
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
                    result: Any = {"error": "Tool is not available in the current tool context"}
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
                    except asyncio.CancelledError:
                        raise
                    except (ToolExecutionError, ValueError, json.JSONDecodeError) as exc:
                        result = {"error": str(exc)}
                api_messages.append(_tool_message(tool_call_id, result))

    # Only reachable when the provider keeps emitting tool calls even though the
    # final round offered it no tools at all.
    raise RuntimeError("AI tool execution exceeded the maximum number of rounds")


def generate_ai_reply_with_tools(
    messages: list[dict],
    *,
    plan: str,
    confirmed: bool = False,
    registry: ToolRegistry,
) -> AIResult:
    """Blocking wrapper around the async tool loop.

    FastAPI runs the synchronous chat endpoint in a worker thread, so there is no
    running event loop here and ``asyncio.run`` is safe. Keeping a single
    implementation prevents the two copies from drifting apart, which is how the
    synchronous path silently lost its retry backoff.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "generate_ai_reply_with_tools() is blocking and cannot be called from an "
            "event loop; await generate_ai_reply_with_tools_async() instead"
        )

    return asyncio.run(
        generate_ai_reply_with_tools_async(
            messages,
            plan=plan,
            confirmed=confirmed,
            registry=registry,
        )
    )
