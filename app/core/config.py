import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    app_name = os.getenv("APP_NAME", "VeloraAi")
    app_env = os.getenv("APP_ENV", "development")
    app_debug = os.getenv("APP_DEBUG", "true").lower() == "true"
    database_url = os.getenv("DATABASE_URL", "sqlite:///./velora.db")


settings = Settings()

