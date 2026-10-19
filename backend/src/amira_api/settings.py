from functools import lru_cache
import logging
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, SecretStr, model_validator

logger = logging.getLogger(__name__)

DEV_SMS_MFA_BYPASS_APP_ENVS = frozenset({"development", "local", "test"})


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
    # Session connection (not the transaction pooler) for LISTEN. Falls back to DATABASE_URL when unset.
    realtime_database_url: str | None = None
    supabase_jwt_issuer: str | None = None
    supabase_jwt_audience: str = "authenticated"
    supabase_publishable_key: SecretStr | None = None
    independent_driver_type_id: UUID | None = None
    company_driver_type_id: UUID | None = None
    email_fallback_secret: SecretStr | None = None
    # Development-only: signs simulated payment checkouts and confirmations. Required for the simulated adapter.
    payment_simulator_secret: SecretStr | None = None
    # Server-to-server secret for POST /api/payments/confirm, sent in the X-Amira-Payment-Webhook-Secret header.
    payment_webhook_secret: SecretStr | None = None
    # Supabase Storage for delivery photos. The service-role key is server-side only; never a NEXT_PUBLIC_* value.
    supabase_url: str | None = None
    supabase_service_role_key: SecretStr | None = None
    # The bucket is private and is created by an operator (see backend/README.md), never by code.
    service_evidence_bucket: str = "service-evidence"
    service_evidence_max_bytes: int = Field(default=8 * 1024 * 1024, gt=0)
    service_evidence_url_ttl_seconds: int = Field(default=300, gt=0)
    service_claim_window_hours: int = Field(default=24, gt=0)
    # Platform commission withheld from each payout, as a whole percent of the gross payment (0 to 99).
    payout_commission_percent: int = Field(default=10, ge=0, lt=100)

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def dev_sms_mfa_bypass_active(self) -> bool:
        # Enforced here as well as in the validator: model_construct skips validation, so the auth path must
        # not rely on it. An unset APP_ENV (default 'development') never activates the bypass.
        return (
            self.dev_skip_sms_mfa
            and "app_env" in self.model_fields_set
            and self.app_env.strip().lower() in DEV_SMS_MFA_BYPASS_APP_ENVS
        )

    @model_validator(mode="after")
    def fail_closed_dev_sms_mfa_bypass_outside_allowlist(self) -> "Settings":
        # Fail closed: an unset APP_ENV (which defaults to an allowlisted value) and any value outside the
        # allowlist (including typos and empty values) refuse the bypass.
        # RuntimeError, not ValueError: pydantic wraps ValueError and echoes every input
        # (including DATABASE_URL) into the traceback, which would leak secrets into logs.
        if self.dev_skip_sms_mfa:
            if "app_env" not in self.model_fields_set:
                raise RuntimeError("DEV_SKIP_SMS_MFA requires APP_ENV to be set explicitly to development, local or test.")
            if self.app_env.strip().lower() not in DEV_SMS_MFA_BYPASS_APP_ENVS:
                allowed = ", ".join(sorted(DEV_SMS_MFA_BYPASS_APP_ENVS))
                raise RuntimeError(f"DEV_SKIP_SMS_MFA requires APP_ENV to be one of: {allowed}.")
        return self


def warn_if_dev_sms_mfa_bypass_active(settings: Settings) -> None:
    if settings.dev_sms_mfa_bypass_active:
        logger.warning("DEV_SKIP_SMS_MFA is enabled: aal1 password sessions skip SMS MFA. Development only.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
