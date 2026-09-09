from pathlib import Path

import pytest

from farmeasy_mandi_analytics.config import (
    CURRENT_MANDI_RESOURCE_ID,
    DEFAULT_PRICE_UNIT,
    ConfigurationError,
    load_settings,
)


def test_settings_use_deterministic_defaults(tmp_path: Path) -> None:
    settings = load_settings(environ={}, project_root=tmp_path)

    assert settings.project_root == tmp_path.resolve()
    assert settings.page_size == 1000
    assert settings.raw_dir == tmp_path / "analytics/data/raw"
    assert settings.enable_arrivals is False
    assert settings.data_gov_api_url == "https://api.data.gov.in/resource"
    assert settings.data_gov_resource_id == CURRENT_MANDI_RESOURCE_ID
    assert settings.price_unit == DEFAULT_PRICE_UNIT
    assert settings.api_rate_limit_per_minute == 120
    assert settings.api_allowed_origins == ()


def test_settings_resolve_relative_paths_and_redact_secrets(tmp_path: Path) -> None:
    settings = load_settings(
        environ={
            "FARMEASY_ANALYTICS_DATABASE_URL": "postgresql+psycopg://user:secret@db/example",
            "FARMEASY_ANALYTICS_DATA_GOV_API_KEY": "not-for-output",
            "FARMEASY_ANALYTICS_API_ACCESS_TOKEN": "analytics-secret",
            "FARMEASY_ANALYTICS_RAW_DIR": "runtime/raw",
        },
        project_root=tmp_path,
    )

    assert settings.raw_dir == tmp_path / "runtime/raw"
    assert settings.redacted()["database_url"] == "***configured***"
    assert settings.redacted()["data_gov_api_key"] == "***configured***"
    assert settings.redacted()["api_access_token"] == "***configured***"
    assert "secret" not in str(settings.redacted())
    assert "not-for-output" not in str(settings.redacted())


def test_settings_parse_api_security_options(tmp_path: Path) -> None:
    settings = load_settings(
        environ={
            "FARMEASY_ANALYTICS_API_RATE_LIMIT_PER_MINUTE": "80",
            "FARMEASY_ANALYTICS_API_ALLOWED_ORIGINS": (
                "https://farmeasy.example, http://localhost:3000/"
            ),
        },
        project_root=tmp_path,
    )

    assert settings.api_rate_limit_per_minute == 80
    assert settings.api_allowed_origins == (
        "https://farmeasy.example",
        "http://localhost:3000",
    )


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("FARMEASY_ANALYTICS_PAGE_SIZE", "0"),
        ("FARMEASY_ANALYTICS_PAGE_SIZE", "5001"),
        ("FARMEASY_ANALYTICS_LOOKBACK_DAYS", "bad"),
        ("FARMEASY_ANALYTICS_ENABLE_ARRIVALS", "perhaps"),
        ("FARMEASY_ANALYTICS_API_RATE_LIMIT_PER_MINUTE", "-1"),
    ],
)
def test_invalid_settings_fail_early(tmp_path: Path, name: str, value: str) -> None:
    with pytest.raises(ConfigurationError):
        load_settings(environ={name: value}, project_root=tmp_path)


def test_required_connection_settings_have_clear_errors(tmp_path: Path) -> None:
    settings = load_settings(environ={}, project_root=tmp_path)

    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        settings.require_database_url()
    with pytest.raises(ConfigurationError, match="DATA_GOV"):
        settings.require_data_gov_credentials()
