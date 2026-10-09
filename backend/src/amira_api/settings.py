from functools import lru_cache
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Amira API"
    app_env: str = "development"
    resend_api_key: SecretStr | None = None
    invitation_sender_email: str | None = None
    frontend_base_url: str | None = None
    cors_origins: str = "http://localhost:3000"
    database_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_publishable_key: SecretStr | None = None
    independent_driver_type_id: UUID | None = None
    company_driver_type_id: UUID | None = None
    email_fallback_secret: SecretStr | None = None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
