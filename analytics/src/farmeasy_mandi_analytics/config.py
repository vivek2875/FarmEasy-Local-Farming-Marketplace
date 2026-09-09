"""Configuration loading for the repeatable analytics pipeline."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from dotenv import load_dotenv

CURRENT_MANDI_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
DEFAULT_PRICE_UNIT = "INR/quintal"


class ConfigurationError(ValueError):
    """Raised when a setting is missing or cannot be used safely."""


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_int(environ: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    raw_value = environ.get(name, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be an integer; received {raw_value!r}.") from error
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}; received {value}.")
    return value


def _read_float(environ: Mapping[str, str], name: str, default: float, minimum: float) -> float:
    raw_value = environ.get(name, str(default)).strip()
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{name} must be numeric; received {raw_value!r}.") from error
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}; received {value}.")
    return value


def _read_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    raw_value = environ.get(name, str(default)).strip().lower()
    valid_values = {"true": True, "1": True, "yes": True, "false": False, "0": False, "no": False}
    if raw_value not in valid_values:
        raise ConfigurationError(f"{name} must be true or false; received {raw_value!r}.")
    return valid_values[raw_value]


def _read_csv(environ: Mapping[str, str], name: str) -> tuple[str, ...]:
    """Read a comma-separated configuration list without empty values."""
    return tuple(
        value.strip().rstrip("/") for value in environ.get(name, "").split(",") if value.strip()
    )


def _read_path(environ: Mapping[str, str], name: str, default: Path, project_root: Path) -> Path:
    raw_value = environ.get(name, "").strip()
    if not raw_value:
        return default
    candidate = Path(raw_value).expanduser()
    return candidate if candidate.is_absolute() else project_root / candidate


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved configuration. Secrets are never included in ``redacted`` output."""

    project_root: Path
    database_url: str | None
    data_gov_api_key: str | None
    data_gov_resource_id: str | None
    data_gov_api_url: str
    price_unit: str
    page_size: int
    lookback_days: int
    request_timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    stale_after_days: int
    suspicious_change_pct: float
    enable_arrivals: bool
    log_level: str
    api_access_token: str | None
    api_rate_limit_per_minute: int
    api_allowed_origins: tuple[str, ...]
    raw_dir: Path
    processed_dir: Path
    quality_reports_dir: Path

    def require_database_url(self) -> str:
        if not self.database_url:
            raise ConfigurationError(
                "FARMEASY_ANALYTICS_DATABASE_URL is required for PostgreSQL loading "
                "and API queries."
            )
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ConfigurationError("FARMEASY_ANALYTICS_DATABASE_URL must use a PostgreSQL URL.")
        return self.database_url

    def require_data_gov_credentials(self) -> tuple[str, str]:
        missing = [
            name
            for name, value in {
                "FARMEASY_ANALYTICS_DATA_GOV_API_KEY": self.data_gov_api_key,
                "FARMEASY_ANALYTICS_DATA_GOV_RESOURCE_ID": self.data_gov_resource_id,
            }.items()
            if not value
        ]
        if missing:
            raise ConfigurationError(
                f"Missing required Data.gov.in setting(s): {', '.join(missing)}."
            )
        return self.data_gov_api_key, self.data_gov_resource_id  # type: ignore[return-value]

    def redacted(self) -> dict[str, object]:
        """Return a display-safe configuration summary for command-line diagnostics."""
        values = asdict(self)
        values["database_url"] = "***configured***" if self.database_url else None
        values["data_gov_api_key"] = "***configured***" if self.data_gov_api_key else None
        values["api_access_token"] = "***configured***" if self.api_access_token else None
        return values


def load_settings(
    environ: Mapping[str, str] | None = None,
    project_root: Path | None = None,
) -> Settings:
    """Load settings from the process environment and the optional root ``.env`` file.

    Supplying ``environ`` makes this function deterministic for tests and prevents
    it from reading a developer's local credentials.
    """
    root = (project_root or _project_root()).resolve()
    if environ is None:
        load_dotenv(root / ".env", override=False)
        environment: Mapping[str, str] = os.environ
    else:
        environment = environ

    raw_dir = _read_path(
        environment,
        "FARMEASY_ANALYTICS_RAW_DIR",
        root / "analytics/data/raw",
        root,
    )
    processed_dir = _read_path(
        environment,
        "FARMEASY_ANALYTICS_PROCESSED_DIR",
        root / "analytics/data/processed",
        root,
    )
    quality_reports_dir = _read_path(
        environment,
        "FARMEASY_ANALYTICS_QUALITY_REPORTS_DIR",
        root / "analytics/data/quality_reports",
        root,
    )
    page_size = _read_int(environment, "FARMEASY_ANALYTICS_PAGE_SIZE", 1000, 1)
    if page_size > 5000:
        raise ConfigurationError("FARMEASY_ANALYTICS_PAGE_SIZE must not exceed 5000.")

    return Settings(
        project_root=root,
        database_url=environment.get("FARMEASY_ANALYTICS_DATABASE_URL") or None,
        data_gov_api_key=environment.get("FARMEASY_ANALYTICS_DATA_GOV_API_KEY") or None,
        data_gov_resource_id=(
            environment.get("FARMEASY_ANALYTICS_DATA_GOV_RESOURCE_ID") or CURRENT_MANDI_RESOURCE_ID
        ),
        data_gov_api_url=(
            environment.get("FARMEASY_ANALYTICS_DATA_GOV_API_URL")
            or "https://api.data.gov.in/resource"
        ).rstrip("/"),
        price_unit=(environment.get("FARMEASY_ANALYTICS_PRICE_UNIT") or DEFAULT_PRICE_UNIT).strip(),
        page_size=page_size,
        lookback_days=_read_int(environment, "FARMEASY_ANALYTICS_LOOKBACK_DAYS", 90, 1),
        request_timeout_seconds=_read_float(
            environment,
            "FARMEASY_ANALYTICS_REQUEST_TIMEOUT_SECONDS",
            30.0,
            0.1,
        ),
        max_retries=_read_int(environment, "FARMEASY_ANALYTICS_MAX_RETRIES", 3, 0),
        retry_backoff_seconds=_read_float(
            environment,
            "FARMEASY_ANALYTICS_RETRY_BACKOFF_SECONDS",
            0.5,
            0.0,
        ),
        stale_after_days=_read_int(environment, "FARMEASY_ANALYTICS_STALE_AFTER_DAYS", 3, 1),
        suspicious_change_pct=_read_float(
            environment,
            "FARMEASY_ANALYTICS_SUSPICIOUS_CHANGE_PCT",
            75.0,
            0.0,
        ),
        enable_arrivals=_read_bool(environment, "FARMEASY_ANALYTICS_ENABLE_ARRIVALS", False),
        log_level=(environment.get("FARMEASY_ANALYTICS_LOG_LEVEL") or "INFO").upper(),
        api_access_token=environment.get("FARMEASY_ANALYTICS_API_ACCESS_TOKEN") or None,
        api_rate_limit_per_minute=_read_int(
            environment,
            "FARMEASY_ANALYTICS_API_RATE_LIMIT_PER_MINUTE",
            120,
            0,
        ),
        api_allowed_origins=_read_csv(environment, "FARMEASY_ANALYTICS_API_ALLOWED_ORIGINS"),
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        quality_reports_dir=quality_reports_dir,
    )
