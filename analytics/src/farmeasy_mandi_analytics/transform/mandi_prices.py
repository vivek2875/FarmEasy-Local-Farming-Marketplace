"""Transform raw official source records into validated mandi-price observations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from farmeasy_mandi_analytics.config import Settings
from farmeasy_mandi_analytics.extract.csv_source import map_source_records
from farmeasy_mandi_analytics.validate.price_rules import (
    PriceValidationResult,
    validate_price_records,
)
from farmeasy_mandi_analytics.validate.standardize import NameStandardizer


def default_alias_config_path(settings: Settings) -> Path:
    return settings.project_root / "analytics/config/name_aliases.json"


def transform_price_records(
    records: Iterable[Mapping[str, Any]],
    *,
    settings: Settings,
    source_name: str,
    reference_date: date | None = None,
    alias_config_path: Path | str | None = None,
) -> PriceValidationResult:
    """Map source headers, standardize names, validate prices, and derive flags.

    The function accepts API JSON records or local CSV records. It deliberately
    does not load a database; persistence is a later pipeline phase.
    """
    aliases = NameStandardizer.from_json(alias_config_path or default_alias_config_path(settings))
    return validate_price_records(
        map_source_records(records),
        source_name=source_name,
        price_unit=settings.price_unit,
        standardizer=aliases,
        reference_date=reference_date,
        stale_after_days=settings.stale_after_days,
        suspicious_change_pct=settings.suspicious_change_pct,
        enable_arrivals=settings.enable_arrivals,
    )
