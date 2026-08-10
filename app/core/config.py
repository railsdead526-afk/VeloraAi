import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    app_name = os.getenv("APP_NAME", "VeloraAi")
    app_env = os.getenv("APP_ENV", "development")
    app_debug = os.getenv("APP_DEBUG", "true").lower() == "true"
    database_url = os.getenv("DATABASE_URL", "sqlite:///./velora.db")

    ai_provider = os.getenv("AI_PROVIDER", "mock")
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")


settings = Settings()

