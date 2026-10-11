from amira_api.settings import Settings


def test_cors_origins_are_parsed_from_comma_separated_setting() -> None:
    settings = Settings(cors_origins="http://localhost:3000, https://example.test")

    assert settings.allowed_origins == ["http://localhost:3000", "https://example.test"]
