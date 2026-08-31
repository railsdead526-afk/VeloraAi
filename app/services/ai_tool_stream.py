from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.ai_provider import auth_headers, build_api_messages, get_provider_config, parse_usage
from app.services.tool_confirmation import create_confirmation_token, verify_confirmation_token
from app.tools.executor import ToolExecutionError, execute_tool
from app.tools.policy import policy
from app.tools.registry import ToolRegistry
from app.tools.selector import select_tools

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 4
MAX_TOOLS_PER_REQUEST = 12
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class AgentStreamEvent:
    type: str
    content: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    confirmation_token: str | None = None


def _tool_message(tool_call_id: str, result: Any) -> dict[str, str]:
    try:
        content = json.dumps(result, ensure_ascii=False)
    except (TypeError, ValueError):
        content = str(result)
    return {"role": "tool", "tool_call_id": tool_call_id, "content": content}


def _parse_tool_arguments(raw_arguments: str) -> dict[str, Any]:
    arguments = json.loads(raw_arguments or "{}")
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


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
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


async def _backoff(attempt: int) -> None:
    await asyncio.sleep(min(2**attempt, 4))


async def stream_ai_reply_with_tools(
    messages: list[dict],
    *,
    db: Session | None = None,
    plan: str,
    confirmed: bool,
    registry: ToolRegistry,
    user_id: int | None = None,
    conversation_id: int | None = None,
    approved_confirmation_token: str | None = None,
) -> AsyncIterator[AgentStreamEvent]:
    config = get_provider_config()
    if config.name == "mock":
        from app.services.ai_service import _mock_result

        result = _mock_result(messages)
        words = result.content.split(" ")
        for index, word in enumerate(words):
            yield AgentStreamEvent(type="token", content=word if index == 0 else f" {word}")
        yield AgentStreamEvent(
            type="done",
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model=result.model,
        )
        return

    if config.name not in {"openai", "llama", "gemini"}:
        raise RuntimeError("AI provider is not configured")
    if config.name in {"openai", "gemini"} and not config.api_key:
        raise RuntimeError("AI provider belum dikonfigurasi")

    api_messages = build_api_messages(messages)
    selected_tools = _selected_tools(registry, messages, plan)
    selected_names = {tool.name for tool in selected_tools}
    call_counts: dict[str, int] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    usage_seen = False

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings.ai_timeout_seconds)) as client:
        for round_index in range(MAX_TOOL_ROUNDS):
            payload: dict[str, Any] = {
                "model": config.model,
                "messages": api_messages,
                "temperature": 0.7,
                "tools": registry.schemas_for(selected_tools),
                "tool_choice": "auto",
                "stream": True,
                "stream_options": {"include_usage": True},
            }

            tool_calls: dict[int, dict[str, str]] = {}
            assistant_content_parts: list[str] = []
            streamed_content = False
            last_error: Exception | None = None

            for attempt in range(settings.ai_max_retries + 1):
                try:
                    async with client.stream(
                        "POST",
                        f"{config.base_url}/chat/completions",
                        headers=auth_headers(config),
                        json=payload,
                    ) as response:
                        if response.status_code in RETRYABLE_STATUS_CODES and attempt < settings.ai_max_retries:
                            await response.aread()
                            await _backoff(attempt)
                            continue
                        response.raise_for_status()

                        async for line in response.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if raw == "[DONE]":
                                continue
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                continue

                            input_tokens, output_tokens = parse_usage(data)
                            if input_tokens is not None and output_tokens is not None:
                                total_input_tokens += input_tokens
                                total_output_tokens += output_tokens
                                usage_seen = True
                                continue

                            choices = data.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content")
                            if content:
                                streamed_content = True
                                assistant_content_parts.append(content)
                                yield AgentStreamEvent(type="token", content=content)

                            for call in delta.get("tool_calls") or []:
                                index = int(call.get("index", 0))
                                state = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                                if call.get("id"):
                                    state["id"] = call["id"]
                                function = call.get("function") or {}
                                if function.get("name"):
                                    state["name"] += function["name"]
                                if function.get("arguments"):
                                    state["arguments"] += function["arguments"]
                        last_error = None
                        break
                except asyncio.CancelledError:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    last_error = exc
                    if streamed_content or attempt >= settings.ai_max_retries or not _is_retryable(exc):
                        break
                    await _backoff(attempt)

            if last_error is not None:
                logger.exception("Streaming AI tool-loop request failed")
                raise RuntimeError("AI service temporarily unavailable") from last_error

            if not tool_calls:
                if not assistant_content_parts:
                    raise RuntimeError("AI provider returned an empty response")
                # if provider didn't return usage, estimate so caller doesn't error
                if not usage_seen:
                    estimated_input = max(1, sum(len(m.get("content","")) for m in api_messages) // 4)
                    estimated_output = max(1, len("".join(assistant_content_parts)) // 4)
                    total_input_tokens = estimated_input
                    total_output_tokens = estimated_output
                    usage_seen = True
                yield AgentStreamEvent(
                    type="done",
                    input_tokens=total_input_tokens if usage_seen else None,
                    output_tokens=total_output_tokens if usage_seen else None,
                    model=config.model,
                )
                return

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": "".join(assistant_content_parts) or None,
                "tool_calls": [],
            }
            for index in sorted(tool_calls):
                call = tool_calls[index]
                assistant_message["tool_calls"].append(
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": call["arguments"] or "{}",
                        },
                    }
                )
            api_messages.append(assistant_message)

            confirmation_required = False
            for call in assistant_message["tool_calls"]:
                name = call["function"]["name"]
                tool_call_id = call["id"]
                yield AgentStreamEvent(type="tool_start", name=name, tool_call_id=tool_call_id)

                if name not in selected_names:
                    result = {"error": "Tool is not available in the current tool context"}
                else:
                    tool = registry.get(name)
                    try:
                        arguments = _parse_tool_arguments(call["function"]["arguments"])
                        approved = False
                        if not policy.requires_approval(tool):
                            approved = True
                        elif confirmed:
                            approved = True
                        elif db is not None and user_id is not None and conversation_id is not None:
                            approved = verify_confirmation_token(
                                db,
                                approved_confirmation_token,
                                user_id=user_id,
                                conversation_id=conversation_id,
                                tool_name=name,
                                arguments=arguments,
                            )

                        if not approved:
                            confirmation_required = True
                            confirmation_token = None
                            if db is not None and user_id is not None and conversation_id is not None:
                                confirmation_token = create_confirmation_token(
                                    db,
                                    user_id=user_id,
                                    conversation_id=conversation_id,
                                    tool_name=name,
                                    arguments=arguments,
                                )
                            yield AgentStreamEvent(
                                type="tool_confirmation_required",
                                name=name,
                                tool_call_id=tool_call_id,
                                confirmation_token=confirmation_token,
                            )
                            result = {"error": "Tool execution requires user confirmation"}
                        else:
                            result = await execute_tool(
                                registry,
                                name=name,
                                arguments=arguments,
                                plan=plan,
                                confirmed=approved,
                                call_counts=call_counts,
                            )
                    except asyncio.CancelledError:
                        raise
                    except (ToolExecutionError, ValueError, json.JSONDecodeError) as exc:
                        result = {"error": str(exc)}

                api_messages.append(_tool_message(tool_call_id, result))
                yield AgentStreamEvent(type="tool_end", name=name, tool_call_id=tool_call_id)

            if confirmation_required:
                return

            if round_index == MAX_TOOL_ROUNDS - 1:
                raise RuntimeError("AI tool execution exceeded the maximum number of rounds")
