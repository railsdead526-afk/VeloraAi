import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.services.ai_provider import (
    SYSTEM_PROMPT,
    build_api_messages,
    get_provider_config,
    parse_usage,
)

logger = logging.getLogger(__name__)


@dataclass
class AIResult:
    content: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    model: str

    def __str__(self) -> str:
        return self.content

    def __eq__(self, other: object) -> bool:
        if isinstance(other, AIResult):
            return self.content == other.content
        if isinstance(other, str):
            return self.content == other
        return NotImplemented


# Backward-compatible helper names for existing imports/tests.
def _build_api_messages(messages: list[dict]) -> list[dict]:
    return build_api_messages(messages)


def _parse_usage(data: dict) -> tuple[Optional[int], Optional[int]]:
    return parse_usage(data)


def _provider_config() -> tuple[str, str, str, str]:
    config = get_provider_config()
    return config.api_key, config.base_url, config.model, config.name


def _request_openai_compatible(messages: list[dict]) -> AIResult:
    config = get_provider_config()
    if config.name == "mock":
        return _mock_result(messages)
    if config.name in {"openai", "gemini"} and not config.api_key:
        raise RuntimeError("AI provider belum dikonfigurasi")

    last_error = None
    for attempt in range(settings.ai_max_retries + 1):
        try:
            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            with httpx.Client(timeout=httpx.Timeout(settings.ai_timeout_seconds)) as client:
                response = client.post(
                    f"{config.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": config.model,
                        "messages": build_api_messages(messages),
                        "temperature": 0.7,
                    },
                )
                if response.status_code in {429, 500, 502, 503, 504} and attempt < settings.ai_max_retries:
                    time.sleep(min(2 ** attempt, 4))
                    continue
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if not content:
                    raise RuntimeError("AI provider returned an empty response")
                input_tokens, output_tokens = parse_usage(data)
                return AIResult(content.strip(), input_tokens, output_tokens, config.model)
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            last_error = exc
            logger.exception("AI provider request failed on attempt %s", attempt + 1)
            if attempt < settings.ai_max_retries:
                time.sleep(min(2 ** attempt, 4))
                continue
            break

    raise RuntimeError("AI service temporarily unavailable") from last_error


def _mock_result(messages: list[dict]) -> AIResult:
    if not messages:
        return AIResult("Halo, ada yang bisa saya bantu?", 0, 0, "mock")

    user_messages = [
        (msg.get("content") or "").strip()
        for msg in messages
        if msg.get("role") == "user" and (msg.get("content") or "").strip()
    ]
    if not user_messages:
        return AIResult("Tolong kirim pesan yang ingin kamu bahas.", 0, 0, "mock")

    current_message = user_messages[-1]
    current_lower = current_message.lower()
    if "pesan saya sebelumnya apa" in current_lower:
        previous_different = next((old for old in reversed(user_messages[:-1]) if old.lower() != current_lower), None)
        reply = f"Pesan kamu sebelumnya adalah: {previous_different}" if previous_different else "Ini adalah pesan pertamamu di percakapan ini."
    elif "pesan pertama saya apa" in current_lower:
        reply = f"Pesan pertama kamu adalah: {user_messages[0]}"
    elif "berapa kali saya sudah kirim pesan" in current_lower:
        reply = f"Kamu sudah mengirim {len(user_messages)} pesan."
    elif "ulangi 2 pesan terakhir saya" in current_lower:
        reply = (
            f"Dua pesan terakhirmu adalah: 1) {user_messages[-2]} 2) {user_messages[-1]}"
            if len(user_messages) >= 2
            else f"Baru ada satu pesan darimu: {user_messages[-1]}"
        )
    else:
        reply = f"Halo, saya menerima pesanmu: {current_message}"

    return AIResult(reply, max(1, sum(len(item.get("content", "")) for item in messages) // 4), max(1, len(reply) // 4), "mock")


def generate_ai_reply_from_history(messages: list[dict]) -> AIResult:
    config = get_provider_config()
    if config.name == "mock":
        return _mock_result(messages)
    if config.name in {"openai", "llama"}:
        return _request_openai_compatible(messages)
    raise RuntimeError("AI provider is not configured")


async def stream_ai_reply_from_history(
    messages: list[dict],
    usage_sink: Optional[dict] = None,
) -> AsyncIterator[str]:
    if usage_sink is not None:
        usage_sink.update({"input_tokens": None, "output_tokens": None, "model": "mock"})

    if not messages:
        yield "Halo, ada yang bisa saya bantu?"
        return

    config = get_provider_config()
    if config.name == "mock":
        result = _mock_result(messages)
        if usage_sink is not None:
            usage_sink.update({"input_tokens": result.input_tokens, "output_tokens": result.output_tokens, "model": result.model})
        words = result.content.split(" ")
        for index, word in enumerate(words):
            yield word if index == 0 else f" {word}"
        return

    if config.name not in {"openai", "llama", "gemini"}:
        raise RuntimeError("AI provider is not configured")
    if config.name in {"openai", "gemini"} and not config.api_key:
        raise RuntimeError("AI provider belum dikonfigurasi")

    last_error = None
    for attempt in range(settings.ai_max_retries + 1):
        streamed_content = False
        try:
            timeout = httpx.Timeout(settings.ai_timeout_seconds)
            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{config.base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": config.model,
                        "messages": build_api_messages(messages),
                        "temperature": 0.7,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    },
                ) as response:
                    if response.status_code in {429, 500, 502, 503, 504} and attempt < settings.ai_max_retries:
                        await response.aread()
                        await _async_backoff(attempt)
                        continue
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            data = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        input_tokens, output_tokens = parse_usage(data)
                        if input_tokens is not None and output_tokens is not None:
                            if usage_sink is not None:
                                usage_sink.update({"input_tokens": input_tokens, "output_tokens": output_tokens, "model": config.model})
                            continue
                        choices = data.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            streamed_content = True
                            yield content
                    return
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            last_error = exc
            logger.exception("AI streaming request failed on attempt %s", attempt + 1)
            if streamed_content:
                break
            if attempt < settings.ai_max_retries:
                await _async_backoff(attempt)
                continue
            break

    raise RuntimeError("AI service temporarily unavailable") from last_error


async def _async_backoff(attempt: int) -> None:
    await asyncio.sleep(min(2 ** attempt, 4))
