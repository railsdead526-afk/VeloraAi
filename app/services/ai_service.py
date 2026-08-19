import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Kamu adalah asisten AI VeloraAi. Jawab dengan jelas, akurat, dan ringkas "
    "kecuali user meminta penjelasan mendalam."
)


def _build_api_messages(messages: list[dict]) -> list[dict]:
    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Keep the most recent context bounded to control latency and token usage.
    recent_messages = messages[-settings.ai_max_history_messages :]
    for msg in recent_messages:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if role in {"user", "assistant", "system"} and content:
            api_messages.append({"role": role, "content": content})
    return api_messages


def generate_ai_reply_from_history(messages: list[dict]) -> str:
    if not messages:
        return "Halo, ada yang bisa saya bantu?"

    if settings.ai_provider == "mock":
        user_messages = [
            (msg.get("content") or "").strip()
            for msg in messages
            if msg.get("role") == "user" and (msg.get("content") or "").strip()
        ]
        if not user_messages:
            return "Tolong kirim pesan yang ingin kamu bahas."

        current_message = user_messages[-1]
        current_lower = current_message.lower()
        if "pesan saya sebelumnya apa" in current_lower:
            previous_different = next(
                (old for old in reversed(user_messages[:-1]) if old.lower() != current_lower),
                None,
            )
            if previous_different:
                return f"Pesan kamu sebelumnya adalah: {previous_different}"
            return "Ini adalah pesan pertamamu di percakapan ini."
        if "pesan pertama saya apa" in current_lower:
            return f"Pesan pertama kamu adalah: {user_messages[0]}"
        if "berapa kali saya sudah kirim pesan" in current_lower:
            return f"Kamu sudah mengirim {len(user_messages)} pesan."
        if "ulangi 2 pesan terakhir saya" in current_lower:
            if len(user_messages) >= 2:
                return f"Dua pesan terakhirmu adalah: 1) {user_messages[-2]} 2) {user_messages[-1]}"
            return f"Baru ada satu pesan darimu: {user_messages[-1]}"
        return f"Halo, saya menerima pesanmu: {current_message}"

    if settings.ai_provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("AI provider belum dikonfigurasi")

        try:
            with httpx.Client(timeout=httpx.Timeout(settings.ai_timeout_seconds)) as client:
                response = client.post(
                    f"{settings.openai_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.openai_model,
                        "messages": _build_api_messages(messages),
                        "temperature": 0.7,
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content")
                if not content:
                    raise RuntimeError("AI provider returned an empty response")
                return content.strip()
        except (httpx.HTTPError, ValueError, KeyError, IndexError) as exc:
            logger.exception("AI provider request failed: %s", exc)
            raise RuntimeError("AI service temporarily unavailable") from exc

    raise RuntimeError("AI provider is not configured")
