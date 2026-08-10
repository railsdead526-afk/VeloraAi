import httpx

from app.core.config import settings


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
            previous_different = None

            for old_message in reversed(user_messages[:-1]):
                if old_message.strip().lower() != current_lower:
                    previous_different = old_message
                    break

            if previous_different:
                return f"Pesan kamu sebelumnya adalah: {previous_different}"

            if len(user_messages) >= 2:
                return f"Pesan kamu sebelumnya adalah: {user_messages[-2]}"

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
            return "OPENAI_API_KEY belum diset."

        api_messages = [
            {
                "role": "system",
                "content": "Kamu adalah asisten AI yang membantu user dengan jawaban singkat, jelas, dan ramah."
            }
        ]

        for msg in messages:
            role = msg.get("role")
            content = (msg.get("content") or "").strip()

            if role in {"user", "assistant", "system"} and content:
                api_messages.append({
                    "role": role,
                    "content": content
                })

        try:
            response = httpx.post(
                f"{settings.openai_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "messages": api_messages,
                    "temperature": 0.7,
                },
                timeout=60.0,
            )

            response.raise_for_status()
            data = response.json()

            return data["choices"][0]["message"]["content"]

        except Exception as e:
            return f"Gagal menghubungi provider AI: {str(e)}"

    return f"Provider AI '{settings.ai_provider}' tidak dikenali."

