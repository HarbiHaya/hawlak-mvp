from functools import lru_cache
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Run from apps/api: ../../.env is the repo-root .env from the README; ./.env overrides it.
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    meta_graph_api_version: str | None = Field(default=None, min_length=1)
    whatsapp_phone_number_id: str | None = Field(default=None, min_length=1)
    whatsapp_access_token: str | None = Field(default=None, min_length=1)
    whatsapp_verify_token: str | None = Field(default=None, min_length=16)
    meta_app_secret: str | None = Field(default=None, min_length=1)
    whatsapp_test_recipient: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")

    # Local-demo access boundary. Replace this token scheme before non-local deployment.
    internal_api_token: SecretStr = Field(min_length=24)
    demo_login_password: SecretStr = Field(min_length=12)
    demo_session_minutes: int = Field(default=480, ge=15, le=1440)
    dashboard_origin: str
    public_base_url: str = "http://localhost:3001"
    hawlak_agent_control_url: str | None = None
    hawlak_control_token: SecretStr | None = Field(default=None, min_length=24)

    # PostgreSQL is the runtime target; SQLite is allowed for isolated unit tests.
    database_url: str = Field(min_length=1)

    # WhatsApp transport. Meta is the demo default; Twilio remains an optional adapter.
    whatsapp_provider: Literal["meta", "twilio"] = "meta"
    twilio_account_sid: str | None = Field(default=None, min_length=34, max_length=34)
    twilio_auth_token: SecretStr | None = Field(default=None, min_length=20)
    twilio_whatsapp_from: str = Field(default="+14155238886", pattern=r"^\+[1-9]\d{7,14}$")

    # Provider adapters are explicit: mock is synthetic-only; live never silently falls back.
    demo_provider_mode: Literal["mock", "live"] = "mock"
    openai_api_key: SecretStr | None = None
    openai_text_model: str = "gpt-6-astra"
    # Reads only the printed label on medicine-box photos.
    openai_vision_model: str = "gpt-4.1-mini"
    elevenlabs_api_key: SecretStr | None = None
    elevenlabs_voice_id: str = "replace_after_saudi_arabic_voice_test"
    elevenlabs_voice_label: str = "Configured Saudi Arabic voice"
    elevenlabs_model_id: str = "eleven_v4"
    elevenlabs_output_format: str = "opus_48000_64"
    elevenlabs_language_code: Literal["ar"] = "ar"
    elevenlabs_stability: float = Field(default=0.35, ge=0, le=1)
    elevenlabs_similarity_boost: float = Field(default=0.8, ge=0, le=1)

    # Hawlak's S3-compatible storage. Local development uses the isolated MinIO service;
    # on AWS leave endpoint and keys unset so the instance role is used.
    s3_endpoint: str | None = Field(default=None, pattern=r"^https?://[^\s]+$")
    s3_region: str = Field(default="us-east-1", min_length=1)
    s3_bucket: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
    s3_access_key: str | None = Field(default=None, min_length=1)
    s3_secret_key: SecretStr | None = Field(default=None, min_length=8)

    @field_validator("dashboard_origin")
    @classmethod
    def validate_dashboard_origin(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("dashboard_origin must be a valid origin") from exc

        has_extra_parts = bool(parsed.path or parsed.query or parsed.fragment or parsed.username)
        local_origin = (
            parsed.scheme == "http"
            and parsed.hostname == "localhost"
            and port is not None
            and parsed.netloc == f"localhost:{port}"
        )
        hosted_origin = parsed.scheme == "https" and bool(parsed.hostname)
        if has_extra_parts or not (local_origin or hosted_origin):
            raise ValueError("dashboard_origin must be localhost HTTP or an HTTPS origin")
        return value.rstrip("/")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        scheme = urlsplit(value).scheme
        if scheme not in {"postgresql", "postgresql+psycopg", "sqlite"}:
            raise ValueError("database_url must use PostgreSQL or SQLite")
        return value

    @field_validator("public_base_url")
    @classmethod
    def validate_public_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("public_base_url must be an absolute HTTP(S) URL")
        if parsed.path or parsed.query or parsed.fragment:
            raise ValueError("public_base_url must not contain a path, query, or fragment")
        return value.rstrip("/")

    @field_validator("hawlak_agent_control_url")
    @classmethod
    def validate_agent_control_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("hawlak_agent_control_url must be an absolute HTTP(S) URL")
        if parsed.path or parsed.query or parsed.fragment:
            raise ValueError("hawlak_agent_control_url must be an origin without a path")
        return value.rstrip("/")

    @model_validator(mode="after")
    def validate_whatsapp_provider(self):
        if self.whatsapp_provider == "meta":
            required = {
                "meta_graph_api_version": self.meta_graph_api_version,
                "whatsapp_phone_number_id": self.whatsapp_phone_number_id,
                "whatsapp_access_token": self.whatsapp_access_token,
                "whatsapp_verify_token": self.whatsapp_verify_token,
                "meta_app_secret": self.meta_app_secret,
            }
            missing = [name for name, value in required.items() if value is None]
            if missing:
                raise ValueError(f"Meta provider requires: {', '.join(missing)}")
            return self
        if self.twilio_account_sid is None or not self.twilio_account_sid.startswith("AC"):
            raise ValueError("twilio_account_sid must be a valid Account SID")
        if self.twilio_auth_token is None:
            raise ValueError("twilio_auth_token is required for the Twilio provider")
        if not self.public_base_url.startswith("https://"):
            raise ValueError("Twilio requires an HTTPS public_base_url")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]
