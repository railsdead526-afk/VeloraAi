from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import settings


SYSTEM_PROMPT = (
    "Kamu adalah asisten AI VeloraAi. Jawab dengan jelas, akurat, dan ringkas "
    "kecuali user meminta penjelasan mendalam."
)


@dataclass(frozen=True)
class AIProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str


SUPPORTED_PROVIDERS = frozenset({"mock", "openai", "llama", "gemini"})


def get_provider_config() -> AIProviderConfig:
    provider = settings.ai_provider
    if provider == "openai":
        return AIProviderConfig("openai", settings.openai_api_key, settings.openai_base_url, settings.openai_model)
    if provider == "llama":
        return AIProviderConfig("llama", settings.llama_api_key, settings.llama_base_url, settings.llama_model)
    if provider == "gemini":
        return AIProviderConfig("gemini", settings.gemini_api_key, settings.gemini_base_url, settings.gemini_model)
    if provider == "mock":
        return AIProviderConfig("mock", "", "", "mock")
    raise RuntimeError("AI provider is not configured")


def is_supported_provider() -> bool:
    return settings.ai_provider in SUPPORTED_PROVIDERS


def build_api_messages(messages: list[dict]) -> list[dict]:
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    recent_messages = messages[-settings.ai_max_history_messages :]
    for msg in recent_messages:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in {"user", "assistant", "system"} and content:
            api_messages.append({"role": role, "content": content})
    return api_messages


def parse_usage(data: dict) -> tuple[Optional[int], Optional[int]]:
    usage = data.get("usage") or {}
    # OpenAI: prompt_tokens/completion_tokens, also handles input_tokens/output_tokens
    # Gemini via OpenAI compat may use promptTokenCount/candidatesTokenCount or totalTokenCount
    input_tokens = (
        usage.get("prompt_tokens")
        or usage.get("input_tokens")
        or usage.get("promptTokenCount")
        or usage.get("prompt_tokens_count")
        or usage.get("inputTokenCount")
    )
    output_tokens = (
        usage.get("completion_tokens")
        or usage.get("output_tokens")
        or usage.get("candidatesTokenCount")
        or usage.get("completion_tokens_count")
        or usage.get("outputTokenCount")
        or usage.get("candidates_token_count")
    )
    # Some providers only return total_tokens; estimate split if needed
    if input_tokens is None and output_tokens is None:
        total = usage.get("total_tokens") or usage.get("totalTokenCount") or usage.get("total_token_count")
        if isinstance(total, int) and total > 0:
            # fallback: split total roughly in half if we can't distinguish
            # caller will refine with actual chunk sizes; here just provide total
            return total // 2, total - total // 2
    if isinstance(input_tokens, int) and isinstance(output_tokens, int):
        return input_tokens, output_tokens
    # allow numeric strings
    try:
        if input_tokens is not None and output_tokens is not None:
            return int(input_tokens), int(output_tokens)
    except (TypeError, ValueError):
        pass
    return None, None


def auth_headers(config: AIProviderConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    return headers
