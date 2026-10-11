"""Keep the test suite independent of the developer's local backend/.env and shell configuration."""

import os

import pytest

from amira_api.settings import Settings, get_settings

ISOLATED_ENV_VARS = ("DEV_SKIP_SMS_MFA", "APP_ENV")

# Runs at collection time, before test modules import amira_api.main, which calls get_settings().
# pydantic-settings reads model_config["env_file"] on every instantiation, so this disables .env loading.
for _name in ISOLATED_ENV_VARS:
    os.environ.pop(_name, None)
Settings.model_config["env_file"] = None
get_settings.cache_clear()


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    # Tests that need the bypass set DEV_SKIP_SMS_MFA or APP_ENV explicitly.
    for name in ISOLATED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
