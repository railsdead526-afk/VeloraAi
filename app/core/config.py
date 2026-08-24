import os
import re

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


class Settings:
    app_name = os.getenv("APP_NAME", "VeloraAi")
    app_env = os.getenv("APP_ENV", "development").lower()
    app_debug = _env_bool("APP_DEBUG", False)
    app_version = os.getenv("APP_VERSION", "0.0.0-dev")
    git_sha = os.getenv("GIT_SHA", "unknown")

    database_url = os.getenv("DATABASE_URL", "sqlite:///./velora.db")
    database_schema = os.getenv("DATABASE_SCHEMA", "public")
    database_pool_size = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    database_max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))
    database_pool_recycle_seconds = int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800"))

    secret_key = os.getenv("SECRET_KEY", "")
    algorithm = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    refresh_token_expire_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
    #: Window after a rotation during which replaying the old refresh token is
    #: treated as two tabs racing rather than as theft. Long enough to cover a
    #: slow request, far too short to be useful to an attacker.
    refresh_rotation_grace_seconds = int(os.getenv("REFRESH_ROTATION_GRACE_SECONDS", "30"))
    max_active_sessions = int(os.getenv("MAX_ACTIVE_SESSIONS", "10"))

    # Encryption keys for third-party credentials stored at rest.
    # Comma-separated; first entry is the active encryption key.
    credential_encryption_keys = os.getenv("CREDENTIAL_ENCRYPTION_KEYS", "")
    # Development escape hatch: resolve tool credentials from process env.
    # Hard-refused in production because it breaks tenant isolation.
    allow_env_tool_credentials = _env_bool("ALLOW_ENV_TOOL_CREDENTIALS", False)

    login_max_failed_attempts = int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "8"))
    login_lockout_minutes = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))
    password_reset_ttl_minutes = int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))
    email_verification_ttl_hours = int(os.getenv("EMAIL_VERIFICATION_TTL_HOURS", "48"))
    require_email_verification = _env_bool("REQUIRE_EMAIL_VERIFICATION", False)
    frontend_base_url = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")

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
    #: Inputs per embeddings request. Providers cap both the array length and the
    #: token count of a single call, so long documents must be sent in batches.
    embedding_batch_size = int(os.getenv("EMBEDDING_BATCH_SIZE", "96"))
    ai_timeout_seconds = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))
    ai_max_history_messages = int(os.getenv("AI_MAX_HISTORY_MESSAGES", "30"))
    ai_max_retries = int(os.getenv("AI_MAX_RETRIES", "2"))

    document_max_upload_bytes = int(os.getenv("DOCUMENT_MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

    #: The maintenance job is expected hourly. Past this age /ready reports the
    #: job as stale: subscriptions stop expiring when it does not run, so the
    #: silence has to be visible.
    maintenance_max_age_minutes = int(os.getenv("MAINTENANCE_MAX_AGE_MINUTES", "180"))

    #: Which gateway handles web checkout. See app/services/payments/registry.py.
    payment_provider = os.getenv("PAYMENT_PROVIDER", "midtrans").strip().lower()

    midtrans_server_key = os.getenv("MIDTRANS_SERVER_KEY", "")
    midtrans_client_key = os.getenv("MIDTRANS_CLIENT_KEY", "")
    midtrans_is_production = _env_bool("MIDTRANS_IS_PRODUCTION", False)
    midtrans_base_url = os.getenv("MIDTRANS_BASE_URL", "https://api.sandbox.midtrans.com")
    midtrans_snap_base_url = os.getenv("MIDTRANS_SNAP_BASE_URL", "https://app.sandbox.midtrans.com")
    payment_timeout_seconds = float(os.getenv("PAYMENT_TIMEOUT_SECONDS", "15"))
    pro_price_idr = int(os.getenv("PRO_PRICE_IDR", "0"))
    max_price_idr = int(os.getenv("MAX_PRICE_IDR", "0"))

    # Billing lifecycle.
    subscription_period_days = int(os.getenv("SUBSCRIPTION_PERIOD_DAYS", "30"))
    subscription_grace_days = int(os.getenv("SUBSCRIPTION_GRACE_DAYS", "3"))
    vat_percent = float(os.getenv("VAT_PERCENT", "0"))

    rate_limit_default = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
    rate_limit_auth = os.getenv("RATE_LIMIT_AUTH", "10/minute")
    rate_limit_chat = os.getenv("RATE_LIMIT_CHAT", "30/minute")
    #: Provider webhooks arrive from a small set of gateway IPs and can burst
    #: during a settlement batch, so this sits well above the default.
    rate_limit_webhook = os.getenv("RATE_LIMIT_WEBHOOK", "240/minute")
    rate_limit_storage_uri = os.getenv("RATE_LIMIT_STORAGE_URI", "memory://")
    cors_origins = _env_list("CORS_ORIGINS")
    trusted_hosts = _env_list("TRUSTED_HOSTS")

    # Outbound email. When SMTP_HOST is empty, verification and reset links are
    # logged instead of delivered; production refuses to boot in that state.
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_username = os.getenv("SMTP_USERNAME", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", "")
    smtp_use_ssl = _env_bool("SMTP_USE_SSL", False)
    smtp_use_starttls = _env_bool("SMTP_USE_STARTTLS", True)
    smtp_timeout_seconds = float(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))

    metrics_enabled = _env_bool("METRICS_ENABLED", True)
    metrics_token = os.getenv("METRICS_TOKEN", "")
    sentry_dsn = os.getenv("SENTRY_DSN", "")
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.database_schema):
            raise RuntimeError("DATABASE_SCHEMA must be a valid PostgreSQL identifier")
        if self.access_token_expire_minutes < 1:
            raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be greater than zero")
        if self.refresh_rotation_grace_seconds < 0 or self.refresh_rotation_grace_seconds > 300:
            raise RuntimeError("REFRESH_ROTATION_GRACE_SECONDS must be between 0 and 300")
        if self.refresh_token_expire_days < 1:
            raise RuntimeError("REFRESH_TOKEN_EXPIRE_DAYS must be greater than zero")
        if self.max_active_sessions < 1:
            raise RuntimeError("MAX_ACTIVE_SESSIONS must be greater than zero")
        if self.login_max_failed_attempts < 1:
            raise RuntimeError("LOGIN_MAX_FAILED_ATTEMPTS must be greater than zero")
        if self.login_lockout_minutes < 1:
            raise RuntimeError("LOGIN_LOCKOUT_MINUTES must be greater than zero")
        if self.password_reset_ttl_minutes < 1:
            raise RuntimeError("PASSWORD_RESET_TTL_MINUTES must be greater than zero")
        if self.email_verification_ttl_hours < 1:
            raise RuntimeError("EMAIL_VERIFICATION_TTL_HOURS must be greater than zero")
        if self.ai_max_history_messages < 1:
            raise RuntimeError("AI_MAX_HISTORY_MESSAGES must be greater than zero")
        if self.ai_timeout_seconds <= 0:
            raise RuntimeError("AI_TIMEOUT_SECONDS must be greater than zero")
        if self.ai_max_retries < 0 or self.ai_max_retries > 5:
            raise RuntimeError("AI_MAX_RETRIES must be between 0 and 5")
        if self.embedding_dimensions != 1536:
            raise RuntimeError(
                "EMBEDDING_DIMENSIONS must remain 1536 until the database vector schema is migrated"
            )
        if self.document_max_upload_bytes < 1024:
            raise RuntimeError("DOCUMENT_MAX_UPLOAD_BYTES must be at least 1024 bytes")
        if self.maintenance_max_age_minutes < 1:
            raise RuntimeError("MAINTENANCE_MAX_AGE_MINUTES must be greater than zero")
        if self.embedding_batch_size < 1 or self.embedding_batch_size > 2048:
            raise RuntimeError("EMBEDDING_BATCH_SIZE must be between 1 and 2048")
        if self.payment_timeout_seconds <= 0:
            raise RuntimeError("PAYMENT_TIMEOUT_SECONDS must be greater than zero")
        if self.pro_price_idr < 0 or self.max_price_idr < 0:
            raise RuntimeError("Plan prices cannot be negative")
        if self.subscription_period_days < 1:
            raise RuntimeError("SUBSCRIPTION_PERIOD_DAYS must be greater than zero")
        if self.subscription_grace_days < 0:
            raise RuntimeError("SUBSCRIPTION_GRACE_DAYS cannot be negative")
        if self.vat_percent < 0 or self.vat_percent > 100:
            raise RuntimeError("VAT_PERCENT must be between 0 and 100")
        if self.database_pool_size < 1:
            raise RuntimeError("DATABASE_POOL_SIZE must be greater than zero")
        if not 1 <= self.smtp_port <= 65535:
            raise RuntimeError("SMTP_PORT must be a valid port number")
        if self.smtp_timeout_seconds <= 0:
            raise RuntimeError("SMTP_TIMEOUT_SECONDS must be greater than zero")
        if self.smtp_host and self.smtp_use_ssl and self.smtp_use_starttls:
            raise RuntimeError("SMTP_USE_SSL and SMTP_USE_STARTTLS are mutually exclusive")
        if self.ai_provider not in {"mock", "openai", "llama"}:
            raise RuntimeError("AI_PROVIDER must be either mock, openai, or llama")
        if not self.payment_provider:
            raise RuntimeError("PAYMENT_PROVIDER must be configured")

        if self.is_production:
            if self.database_schema == "public":
                raise RuntimeError("DATABASE_SCHEMA must not be public in production")
            if self.ai_provider == "mock":
                raise RuntimeError("AI_PROVIDER=mock is only allowed outside production")
            if not self.secret_key or self.secret_key == "change-this-secret-key":  # noqa: S105
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
            if any(origin.startswith("http://") for origin in self.cors_origins):
                raise RuntimeError("CORS_ORIGINS must use https in production")
            if not self.trusted_hosts:
                raise RuntimeError("TRUSTED_HOSTS must be configured in production")
            if "*" in self.trusted_hosts:
                raise RuntimeError("TRUSTED_HOSTS must not use * in production")
            # A deployment that sells nothing needs no gateway and no prices.
            # PAYMENT_PROVIDER=disabled makes that an explicit choice rather
            # than the accident of leaving credentials blank.
            if self.payment_provider == "midtrans":
                if not self.midtrans_server_key or not self.midtrans_client_key:
                    raise RuntimeError("Midtrans credentials must be configured in production")
                if self.pro_price_idr <= 0 or self.max_price_idr <= 0:
                    raise RuntimeError("Pro and Max prices must be configured in production")
            if not self.credential_encryption_keys:
                raise RuntimeError(
                    "CREDENTIAL_ENCRYPTION_KEYS must be configured in production; "
                    "third-party credentials cannot be stored without it"
                )
            if self.allow_env_tool_credentials:
                raise RuntimeError(
                    "ALLOW_ENV_TOOL_CREDENTIALS must be false in production; "
                    "shared process-level tool credentials break tenant isolation"
                )
            if not self.require_email_verification:
                raise RuntimeError("REQUIRE_EMAIL_VERIFICATION must be true in production")
            if not self.frontend_base_url.startswith("https://"):
                raise RuntimeError("FRONTEND_BASE_URL must use https in production")
            if self.metrics_enabled and not self.metrics_token:
                raise RuntimeError(
                    "METRICS_TOKEN must be set when metrics are enabled in production"
                )
            if not self.smtp_host:
                raise RuntimeError(
                    "SMTP_HOST must be configured in production; email verification and "
                    "password reset are unusable without a delivery transport"
                )
            if not self.smtp_from and not self.smtp_username:
                raise RuntimeError(
                    "SMTP_FROM or SMTP_USERNAME must be set to address outbound mail"
                )

        # Outside production we still refuse a silently-broken crypto config.
        if self.credential_encryption_keys:
            from app.core.crypto import SecretBox

            SecretBox.from_env_value(self.credential_encryption_keys)


settings = Settings()
settings.validate()
