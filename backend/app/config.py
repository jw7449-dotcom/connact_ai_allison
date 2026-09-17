from pathlib import Path
from datetime import datetime
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import BaseModel, Field, field_validator


class AIProviderConfig(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=30)
    label: str = Field(min_length=1, max_length=80)
    base_url: str
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    models: list[str] = Field(min_length=1)
    protocol: Literal["compatible", "anthropic"] = "compatible"
    token_parameter: Literal["max_tokens", "max_completion_tokens"] = "max_tokens"
    json_mode: bool = True
    thinking_mode: Literal["auto", "enabled", "disabled", "default"] = "auto"

    @field_validator("base_url")
    @classmethod
    def valid_endpoint(cls, value):
        from urllib.parse import urlsplit

        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "Use an HTTP(S) base URL without credentials, query or fragment"
            )
        return value.rstrip("/")

    @field_validator("models")
    @classmethod
    def valid_models(cls, values):
        if any(not v.strip() or len(v.strip()) > 118 for v in values):
            raise ValueError("Model IDs must contain 1-118 characters")
        return list(dict.fromkeys(v.strip() for v in values))


ROOT = (
    Path(__file__).resolve().parents[1]
)  # backend directory; .env lives one level above


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT.parent / ".env", ROOT / ".env"), extra="ignore"
    )
    database_url: str = (
        "postgresql+psycopg://meridian:meridian@127.0.0.1:54329/meridian"
    )
    workspace_id: str = "local-personal"
    upload_dir: str = str(ROOT.parent / "data" / "uploads")
    people_mode: Literal["mock", "live"] = "mock"
    public_search_mode: Literal["mock", "live"] = "mock"
    ai_mode: Literal["mock", "live"] = "mock"
    apollo_api_key: str = ""
    serpapi_api_key: str = ""
    ai_api_key: str = ""
    ai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ai_model: str = "qwen-plus"
    ai_provider: str = "bailian"
    ai_models: str = ""
    ai_default_model: str = ""
    # Entries override matching presets or add a custom provider. Secrets stay server-side.
    ai_providers: list[AIProviderConfig] = []
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    dashscope_api_key: str = ""
    ai_timeout_seconds: float = 60
    apify_api_key: str = ""
    apify_profile_actor: str = "harvestapi/linkedin-profile-scraper"
    apify_max_charge_usd: float = 0.05
    people_cache_hours: int = 168
    auth_mode: Literal["local", "invite", "open"] = "local"
    auth_provider: Literal["password", "google"] = "password"
    google_client_id: str = ""
    google_client_secret: str = ""
    # Separate mailbox consent; optionally reuse the sign-in OAuth client.
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_token_encryption_keys: str = ""
    gmail_worker_enabled: bool = True
    gmail_sync_interval_seconds: int = Field(default=120, ge=30, le=3600)
    gmail_daily_send_limit: int = Field(default=100, ge=1, le=2000)
    bootstrap_admin_password_hash: str = ""
    public_origin: str = "http://127.0.0.1:3100"
    allowed_hosts: str = "localhost,127.0.0.1,backend,testserver"
    session_days: int = 7
    provider_calls_per_minute: int = 20
    render_external_hostname: str = ""
    bootstrap_invite_email: str = ""
    bootstrap_invite_token_hash: str = ""
    bootstrap_invite_max_uses: int = Field(default=1, ge=1, le=1000)
    bootstrap_invite_expires_at: datetime | None = None

    @field_validator("public_origin")
    @classmethod
    def canonical_public_origin(cls, value):
        from urllib.parse import urlsplit

        value = value.strip().rstrip("/")
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https") or not url.hostname
            or url.username or url.password or url.path or url.query or url.fragment
            or "\\" in value or any(c.isspace() or ord(c) < 32 for c in value)
            or (url.scheme == "http" and url.hostname not in ("localhost", "127.0.0.1", "::1"))
        ):
            raise ValueError("PUBLIC_ORIGIN must be an HTTPS origin (HTTP only for localhost), without a path or credentials.")
        # Validate the port as well; callback URLs must come from trusted configuration.
        _ = url.port
        return value

    @field_validator("bootstrap_invite_expires_at")
    @classmethod
    def invitation_expiry_has_timezone(cls, value):
        if value is not None and value.utcoffset() is None:
            raise ValueError("Invitation expiry must include a timezone.")
        return value

    @field_validator("database_url")
    @classmethod
    def postgres_driver(cls, value):
        # Render supplies a standard Postgres URL; this app uses psycopg 3.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @field_validator("upload_dir")
    @classmethod
    def local_upload_path(cls, value):
        path = Path(value)
        return str(path if path.is_absolute() else (ROOT.parent / path).resolve())


settings = Settings()
