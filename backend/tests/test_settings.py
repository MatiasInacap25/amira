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


def test_payout_commission_defaults_to_ten_percent() -> None:
    assert Settings(_env_file=None).payout_commission_percent == 10


def test_payout_commission_accepts_zero_and_values_below_one_hundred() -> None:
    assert Settings(_env_file=None, payout_commission_percent=0).payout_commission_percent == 0
    assert Settings(_env_file=None, payout_commission_percent=99).payout_commission_percent == 99


def test_payout_commission_rejects_one_hundred_and_negative_values() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, payout_commission_percent=100)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, payout_commission_percent=-1)


def test_service_evidence_settings_reject_non_positive_values() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, service_evidence_max_bytes=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, service_evidence_url_ttl_seconds=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, service_claim_window_hours=0)
