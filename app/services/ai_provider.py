from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


@dataclass(frozen=True)
class AIProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str


SUPPORTED_PROVIDERS = frozenset({"mock", "openai", "llama"})


def get_provider_config() -> AIProviderConfig:
    provider = settings.ai_provider
    if provider == "openai":
        return AIProviderConfig("openai", settings.openai_api_key, settings.openai_base_url, settings.openai_model)
    if provider == "llama":
        return AIProviderConfig("llama", settings.llama_api_key, settings.llama_base_url, settings.llama_model)
    if provider == "mock":
        return AIProviderConfig("mock", "", "", "mock")
    raise RuntimeError("AI provider is not configured")


def is_supported_provider() -> bool:
    return settings.ai_provider in SUPPORTED_PROVIDERS


def build_api_messages(messages: list[dict]) -> list[dict]:
    api_messages = [{"role": "system", "content": settings.system_prompt}]
    recent_messages = messages[-settings.ai_max_history_messages :]
    for msg in recent_messages:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in {"user", "assistant", "system"} and content:
            api_messages.append({"role": role, "content": content})
    return api_messages


def parse_usage(data: dict) -> tuple[Optional[int], Optional[int]]:
    usage = data.get("usage") or {}
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return input_tokens, output_tokens
    return None, None


def auth_headers(config: AIProviderConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers
