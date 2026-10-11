from functools import lru_cache
import logging
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, model_validator

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Amira API"
    app_env: str = "development"
    # Development-only: lets an aal1 password session skip SMS MFA. Never enabled in production.
    dev_skip_sms_mfa: bool = False
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

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() == "production"

    @property
    def dev_sms_mfa_bypass_active(self) -> bool:
        return self.dev_skip_sms_mfa and not self.is_production

    @model_validator(mode="after")
    def reject_dev_sms_mfa_bypass_in_production(self) -> "Settings":
        # RuntimeError, not ValueError: pydantic wraps ValueError and echoes every input
        # (including DATABASE_URL) into the traceback, which would leak secrets into logs.
        if self.dev_skip_sms_mfa and self.is_production:
            raise RuntimeError("DEV_SKIP_SMS_MFA must not be enabled when APP_ENV is 'production'.")
        return self


def warn_if_dev_sms_mfa_bypass_active(settings: Settings) -> None:
    if settings.dev_sms_mfa_bypass_active:
        logger.warning("DEV_SKIP_SMS_MFA is enabled: aal1 password sessions skip SMS MFA. Development only.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
