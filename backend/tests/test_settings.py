import pytest
from pydantic import ValidationError

from amira_api.settings import Settings


def test_cors_origins_are_parsed_from_comma_separated_setting() -> None:
    settings = Settings(cors_origins="http://localhost:3000, https://example.test")

    assert settings.allowed_origins == ["http://localhost:3000", "https://example.test"]


def test_service_evidence_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.supabase_url is None
    assert settings.supabase_service_role_key is None
    assert settings.service_evidence_bucket == "service-evidence"
    assert settings.service_evidence_max_bytes == 8 * 1024 * 1024
    assert settings.service_evidence_url_ttl_seconds == 300
    assert settings.service_claim_window_hours == 24


def test_service_evidence_settings_reject_non_positive_values() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, service_evidence_max_bytes=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, service_evidence_url_ttl_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, service_claim_window_hours=0)
