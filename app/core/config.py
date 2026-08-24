import ipaddress
import os
import re
from dotenv import load_dotenv

load_dotenv()


class Settings:
    app_name = os.getenv("APP_NAME", "VeloraAi")
    app_env = os.getenv("APP_ENV", "development").lower()
    app_debug = os.getenv("APP_DEBUG", "false").lower() == "true"
    database_url = os.getenv("DATABASE_URL", "sqlite:///./velora.db")
    database_schema = os.getenv("DATABASE_SCHEMA", "public")

    secret_key = os.getenv("SECRET_KEY", "")
    algorithm = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

    ai_provider = os.getenv("AI_PROVIDER", "mock").lower()
    openai_api_key = os.getenv("OPENAI_API_KEY", "")
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    llama_api_key = os.getenv("LLAMA_API_KEY", "")
    llama_model = os.getenv("LLAMA_MODEL", "Llama-3.1-8B-Instruct")
    llama_base_url = os.getenv("LLAMA_BASE_URL", "http://localhost:11434/v1").rstrip("/")
    embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    embedding_base_url = os.getenv("EMBEDDING_BASE_URL", "").rstrip("/")
    embedding_api_key = os.getenv("EMBEDDING_API_KEY", "")
    embedding_dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    ai_timeout_seconds = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))
    ai_max_history_messages = int(os.getenv("AI_MAX_HISTORY_MESSAGES", "30"))
    ai_max_retries = int(os.getenv("AI_MAX_RETRIES", "2"))

    document_max_upload_bytes = int(os.getenv("DOCUMENT_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
    max_request_body_bytes = int(os.getenv("MAX_REQUEST_BODY_BYTES", str(12 * 1024 * 1024)))
    rag_worker_poll_seconds = float(os.getenv("RAG_WORKER_POLL_SECONDS", "5"))
    rag_worker_batch_size = int(os.getenv("RAG_WORKER_BATCH_SIZE", "4"))
    rag_processing_stale_seconds = int(os.getenv("RAG_PROCESSING_STALE_SECONDS", "900"))

    midtrans_server_key = os.getenv("MIDTRANS_SERVER_KEY", "")
    midtrans_client_key = os.getenv("MIDTRANS_CLIENT_KEY", "")
    midtrans_is_production = os.getenv("MIDTRANS_IS_PRODUCTION", "false").lower() == "true"
    midtrans_base_url = os.getenv("MIDTRANS_BASE_URL", "https://api.sandbox.midtrans.com")
    midtrans_snap_base_url = os.getenv("MIDTRANS_SNAP_BASE_URL", "https://app.sandbox.midtrans.com")
    payment_timeout_seconds = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "15"))
    pro_price_idr = int(os.getenv("PRO_PRICE_IDR", "0"))
    max_price_idr = int(os.getenv("MAX_PRICE_IDR", "0"))

    rate_limit_default = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
    rate_limit_auth = os.getenv("RATE_LIMIT_AUTH", "10/minute")
    rate_limit_chat = os.getenv("RATE_LIMIT_CHAT", "30/minute")
    rate_limit_storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
    cors_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    trusted_proxy_ips = [value.strip() for value in os.getenv("TRUSTED_PROXY_IPS", "").split(",") if value.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.database_schema):
            raise RuntimeError("DATABASE_SCHEMA must be a valid PostgreSQL identifier")
        if self.access_token_expire_minutes < 1:
            raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero")
        if self.ai_max_history_messages < 1:
            raise RuntimeError("AI_MAX_HISTORY_MESSAGES must be greater than zero")
        if self.ai_timeout_seconds <= 0:
            raise RuntimeError("AI_TIMEOUT_SECONDS must be greater than zero")
        if self.ai_max_retries < 0 or self.ai_max_retries > 5:
            raise RuntimeError("AI_MAX_RETRIES must be between 0 and 5")
        if self.embedding_dimensions != 1536:
            raise RuntimeError("EMBEDDING_DIMENSIONS must remain 1536 until the database vector schema is migrated")
        if self.document_max_upload_bytes < 1024:
            raise RuntimeError("DOCUMENT_MAX_UPLOAD_BYTES must be at least 1024 bytes")
        if self.max_request_body_bytes < self.document_max_upload_bytes:
            raise RuntimeError("MAX_REQUEST_BODY_BYTES must be at least DOCUMENT_MAX_UPLOAD_BYTES")
        if self.rag_worker_poll_seconds <= 0:
            raise RuntimeError("RAG_WORKER_POLL_SECONDS must be greater than zero")
        if self.rag_worker_batch_size < 1 or self.rag_worker_batch_size > 100:
            raise RuntimeError("RAG_WORKER_BATCH_SIZE must be between 1 and 100")
        if self.rag_processing_stale_seconds < 60:
            raise RuntimeError("RAG_PROCESSING_STALE_SECONDS must be at least 60 seconds")
        if self.payment_timeout_seconds <= 0:
            raise RuntimeError("PAYMENT_TIMEOUT_SECONDS must be greater than zero")
        if self.pro_price_idr < 0 or self.max_price_idr < 0:
            raise RuntimeError("Plan prices cannot be negative")
        if self.ai_provider not in {"mock", "openai", "llama"}:
            raise RuntimeError("AI_PROVIDER must be either mock, openai, or llama")
        for proxy in self.trusted_proxy_ips:
            try:
                ipaddress.ip_network(proxy, strict=False)
            except ValueError as exc:
                raise RuntimeError(f"TRUSTED_PROXY_IPS contains an invalid IP or network: {proxy}") from exc

        if self.is_production:
            if self.database_schema == "public":
                raise RuntimeError("DATABASE_SCHEMA must not be public in production")
            if self.ai_provider == "mock":
                raise RuntimeError("AI_PROVIDER=mock is only allowed outside production")
            if not self.secret_key or self.secret_key == "change-this-secret-key":
                raise RuntimeError("SECRET_KEY must be configured in production")
            if len(self.secret_key) < 32:
                raise RuntimeError("SECRET_KEY must be at least 32 characters in production")
            if self.algorithm != "HS256":
                raise RuntimeError("Only HS256 is currently supported")
            if self.app_debug:
                raise RuntimeError("APP_DEBUG must be false in production")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg2://")):
                raise RuntimeError("Production DATABASE_URL must use PostgreSQL")
            if self.ai_provider == "openai" and not self.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY must be configured when AI_PROVIDER=openai")
            if self.ai_provider == "llama" and not self.llama_base_url:
                raise RuntimeError("LLAMA_BASE_URL must be configured when AI_PROVIDER=llama")
            if self.rate_limit_storage_uri == "memory://":
                raise RuntimeError("RATE_LIMIT_STORAGE_URI must use shared storage in production")
            if not self.cors_origins:
                raise RuntimeError("CORS_ORIGINS must be configured in production")
            if "*" in self.cors_origins:
                raise RuntimeError("CORS_ORIGINS must not use * when credentials are enabled")
            if not self.midtrans_server_key or not self.midtrans_client_key:
                raise RuntimeError("Midtrans credentials must be configured in production")
            if not self.midtrans_is_production:
                raise RuntimeError("MIDTRANS_IS_PRODUCTION must be true in production")
            if self.midtrans_base_url != "https://api.midtrans.com":
                raise RuntimeError("MIDTRANS_BASE_URL must use the production Midtrans API endpoint")
            if self.midtrans_snap_base_url != "https://app.midtrans.com":
                raise RuntimeError("MIDTRANS_SNAP_BASE_URL must use the production Midtrans Snap endpoint")
            if self.pro_price_idr <= 0 or self.max_price_idr <= 0:
                raise RuntimeError("Pro and Max prices must be configured in production")


settings = Settings()
settings.validate()
