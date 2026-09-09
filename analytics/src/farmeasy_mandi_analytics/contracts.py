"""Stable data contracts shared by extraction, quality, and warehouse layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

CANONICAL_PRICE_FIELDS = (
    "market_date",
    "state",
    "district",
    "market",
    "commodity",
    "variety",
    "grade",
    "min_price",
    "max_price",
    "modal_price",
    "price_unit",
    "arrival_quantity",
    "arrival_unit",
    "source_name",
    "source_record_id",
)

REQUIRED_PRICE_FIELDS = (
    "market_date",
    "state",
    "district",
    "market",
    "commodity",
    "min_price",
    "max_price",
    "modal_price",
)


class QualitySeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class QualityIssueCode(StrEnum):
    MISSING_REQUIRED_VALUE = "missing_required_value"
    INVALID_DATE = "invalid_date"
    NON_NUMERIC_PRICE = "non_numeric_price"
    NON_POSITIVE_PRICE = "non_positive_price"
    INVALID_PRICE_RANGE = "invalid_price_range"
    MODAL_PRICE_OUTSIDE_RANGE = "modal_price_outside_range"
    DUPLICATE_OBSERVATION = "duplicate_observation"
    SUSPICIOUS_PRICE_CHANGE = "suspicious_price_change"
    MISSING_REPORTING_DATE = "missing_reporting_date"
    STALE_MARKET = "stale_market"
    INVALID_ARRIVAL_UNIT = "invalid_arrival_unit"
    INVALID_ARRIVAL_QUANTITY = "invalid_arrival_quantity"
    MIXED_ARRIVAL_UNITS = "mixed_arrival_units"
    CONFLICTING_OBSERVATION = "conflicting_observation"
    SOURCE_REQUEST_FAILED = "source_request_failed"


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    """An auditable finding; records are never silently discarded."""

    code: QualityIssueCode
    severity: QualitySeverity
    reason: str
    source_row_number: int | None = None
    source_observation_hash: str | None = None
    field_name: str | None = None
    record: dict[str, Any] | None = None


@dataclass(slots=True)
class DataQualitySummary:
    raw_rows_received: int = 0
    valid_rows_loaded: int = 0
    duplicates_removed: int = 0
    invalid_rows_rejected: int = 0
    suspicious_price_count: int = 0
    conflicting_observation_count: int = 0
    missing_value_counts: dict[str, int] = field(default_factory=dict)
    stale_market_count: int = 0
    missing_reporting_date_count: int = 0
    data_freshness_date: str | None = None
    pipeline_executed_at: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineRunResult:
    """Counts and timestamps persisted later in ``pipeline_run_log``."""

    run_id: str
    source_name: str
    started_at: str
    finished_at: str | None
    status: str
    summary: DataQualitySummary
