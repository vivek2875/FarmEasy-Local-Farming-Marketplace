"""Idempotent PostgreSQL loading for validated mandi-price observations."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from farmeasy_mandi_analytics.config import Settings
from farmeasy_mandi_analytics.contracts import DataQualityIssue
from farmeasy_mandi_analytics.validate.price_rules import PriceValidationResult

CORE_SCHEMA_FILENAME = "001_analytics_schema.sql"
DASHBOARD_VIEWS_FILENAME = "001_dashboard_views.sql"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SENSITIVE_CONFIGURATION_KEY_PARTS = (
    "apikey",
    "authorization",
    "credential",
    "databaseurl",
    "dburl",
    "password",
    "privatekey",
    "secret",
    "token",
)
_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class WarehouseError(RuntimeError):
    """Raised without exposing connection details when warehouse work fails."""


@dataclass(frozen=True, slots=True)
class WarehouseLoadResult:
    """Counters persisted for one successful warehouse load."""

    run_id: str
    source_name: str
    valid_price_rows_received: int
    fact_rows_affected: int
    quality_issues_logged: int


_START_RUN_SQL = text(
    """
    INSERT INTO analytics.pipeline_run_log (
        run_id, source_name, raw_manifest_path, status, started_at,
        raw_rows_received, valid_rows_loaded, invalid_rows_rejected,
        duplicates_removed, conflicting_observation_count, suspicious_price_count,
        missing_reporting_date_count, stale_market_count, data_freshness_date,
        configuration_snapshot, error_summary, updated_at
    ) VALUES (
        :run_id, :source_name, :raw_manifest_path, 'running', NOW(),
        :raw_rows_received, :valid_rows_loaded, :invalid_rows_rejected,
        :duplicates_removed, :conflicting_observation_count, :suspicious_price_count,
        :missing_reporting_date_count, :stale_market_count, :data_freshness_date,
        CAST(:configuration_snapshot AS jsonb), NULL, NOW()
    )
    ON CONFLICT (run_id) DO UPDATE SET
        source_name = EXCLUDED.source_name,
        raw_manifest_path = EXCLUDED.raw_manifest_path,
        status = 'running',
        started_at = NOW(),
        completed_at = NULL,
        raw_rows_received = EXCLUDED.raw_rows_received,
        valid_rows_loaded = EXCLUDED.valid_rows_loaded,
        invalid_rows_rejected = EXCLUDED.invalid_rows_rejected,
        duplicates_removed = EXCLUDED.duplicates_removed,
        conflicting_observation_count = EXCLUDED.conflicting_observation_count,
        suspicious_price_count = EXCLUDED.suspicious_price_count,
        missing_reporting_date_count = EXCLUDED.missing_reporting_date_count,
        stale_market_count = EXCLUDED.stale_market_count,
        data_freshness_date = EXCLUDED.data_freshness_date,
        fact_rows_affected = 0,
        quality_issues_logged = 0,
        configuration_snapshot = EXCLUDED.configuration_snapshot,
        error_summary = NULL,
        updated_at = NOW()
    """
)

_FINISH_RUN_SQL = text(
    """
    UPDATE analytics.pipeline_run_log
    SET status = 'succeeded',
        completed_at = NOW(),
        fact_rows_affected = :fact_rows_affected,
        quality_issues_logged = :quality_issues_logged,
        updated_at = NOW()
    WHERE run_id = :run_id
    """
)

_FAIL_RUN_SQL = text(
    """
    UPDATE analytics.pipeline_run_log
    SET status = 'failed',
        completed_at = NOW(),
        error_summary = :error_summary,
        updated_at = NOW()
    WHERE run_id = :run_id
    """
)

_UPSERT_DATE_SQL = text(
    """
    INSERT INTO analytics.dim_date (
        date_key, full_date, calendar_year, calendar_quarter, calendar_month,
        month_name, iso_week, day_of_month, day_of_week, day_name, is_weekend
    ) VALUES (
        :date_key, :full_date, :calendar_year, :calendar_quarter, :calendar_month,
        :month_name, :iso_week, :day_of_month, :day_of_week, :day_name, :is_weekend
    )
    ON CONFLICT (date_key) DO NOTHING
    """
)

_UPSERT_LOCATION_SQL = text(
    """
    INSERT INTO analytics.dim_location (
        state_name, state_normalized, district_name, district_normalized
    ) VALUES (
        :state_name, :state_normalized, :district_name, :district_normalized
    )
    ON CONFLICT (state_normalized, district_normalized) DO UPDATE SET
        state_name = EXCLUDED.state_name,
        district_name = EXCLUDED.district_name,
        updated_at = NOW()
    RETURNING location_key
    """
)

_UPSERT_MARKET_SQL = text(
    """
    INSERT INTO analytics.dim_market (location_key, market_name, market_normalized)
    VALUES (:location_key, :market_name, :market_normalized)
    ON CONFLICT (location_key, market_normalized) DO UPDATE SET
        market_name = EXCLUDED.market_name,
        updated_at = NOW()
    RETURNING market_key
    """
)

_UPSERT_COMMODITY_SQL = text(
    """
    INSERT INTO analytics.dim_commodity (
        commodity_name, commodity_normalized, variety_name, variety_normalized,
        grade_name, grade_normalized
    ) VALUES (
        :commodity_name, :commodity_normalized, :variety_name, :variety_normalized,
        :grade_name, :grade_normalized
    )
    ON CONFLICT (commodity_normalized, variety_normalized, grade_normalized) DO UPDATE SET
        commodity_name = EXCLUDED.commodity_name,
        variety_name = EXCLUDED.variety_name,
        grade_name = EXCLUDED.grade_name,
        updated_at = NOW()
    RETURNING commodity_key
    """
)

_UPSERT_FACT_SQL = text(
    """
    INSERT INTO analytics.fact_mandi_prices (
        source_name, source_record_id, source_observation_hash, source_content_hash,
        date_key, market_key, commodity_key, min_price, max_price, modal_price,
        price_unit, price_spread, price_spread_pct, quality_status,
        quality_warning_codes, first_loaded_run_id, last_loaded_run_id
    ) VALUES (
        :source_name, :source_record_id, :source_observation_hash, :source_content_hash,
        :date_key, :market_key, :commodity_key, :min_price, :max_price, :modal_price,
        :price_unit, :price_spread, :price_spread_pct, :quality_status,
        :quality_warning_codes, :run_id, :run_id
    )
    ON CONFLICT (source_name, source_observation_hash) DO UPDATE SET
        source_record_id = EXCLUDED.source_record_id,
        source_content_hash = EXCLUDED.source_content_hash,
        date_key = EXCLUDED.date_key,
        market_key = EXCLUDED.market_key,
        commodity_key = EXCLUDED.commodity_key,
        min_price = EXCLUDED.min_price,
        max_price = EXCLUDED.max_price,
        modal_price = EXCLUDED.modal_price,
        price_unit = EXCLUDED.price_unit,
        price_spread = EXCLUDED.price_spread,
        price_spread_pct = EXCLUDED.price_spread_pct,
        quality_status = EXCLUDED.quality_status,
        quality_warning_codes = EXCLUDED.quality_warning_codes,
        last_loaded_run_id = EXCLUDED.last_loaded_run_id,
        last_loaded_at = NOW(),
        updated_at = NOW()
    WHERE analytics.fact_mandi_prices.source_content_hash
            IS DISTINCT FROM EXCLUDED.source_content_hash
       OR analytics.fact_mandi_prices.source_record_id
            IS DISTINCT FROM EXCLUDED.source_record_id
       OR analytics.fact_mandi_prices.quality_status
            IS DISTINCT FROM EXCLUDED.quality_status
       OR analytics.fact_mandi_prices.quality_warning_codes
            IS DISTINCT FROM EXCLUDED.quality_warning_codes
    """
)

_INSERT_QUALITY_ISSUE_SQL = text(
    """
    INSERT INTO analytics.data_quality_log (
        run_id, source_name, issue_hash, issue_code, severity, reason,
        source_row_number, source_observation_hash, field_name, record_context
    ) VALUES (
        :run_id, :source_name, :issue_hash, :issue_code, :severity, :reason,
        :source_row_number, :source_observation_hash, :field_name,
        CAST(:record_context AS jsonb)
    )
    ON CONFLICT (run_id, issue_hash) DO NOTHING
    """
)


def _as_text(value: Any, *, field_name: str, allow_unknown: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        if allow_unknown:
            return "Unknown"
        raise WarehouseError(f"Validated record has no {field_name}.")
    rendered = str(value).strip()
    if not rendered or rendered == "<NA>":
        if allow_unknown:
            return "Unknown"
        raise WarehouseError(f"Validated record has no {field_name}.")
    return rendered


def _as_normalized_text(value: Any, *, field_name: str, allow_unknown: bool = False) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        if allow_unknown:
            return "unknown"
        raise WarehouseError(f"Validated record has no normalized {field_name}.")
    rendered = str(value).strip()
    if not rendered or rendered == "<NA>":
        if allow_unknown:
            return "unknown"
        raise WarehouseError(f"Validated record has no normalized {field_name}.")
    return rendered


def _nullable_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    rendered = str(value).strip()
    return None if not rendered or rendered == "<NA>" else rendered


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise WarehouseError("Validated record has an invalid market_date.") from error
    raise WarehouseError("Validated record has an invalid market_date.")


def _date_dimensions(value: date) -> dict[str, Any]:
    iso_calendar = value.isocalendar()
    return {
        "date_key": int(value.strftime("%Y%m%d")),
        "full_date": value,
        "calendar_year": value.year,
        "calendar_quarter": ((value.month - 1) // 3) + 1,
        "calendar_month": value.month,
        "month_name": _MONTH_NAMES[value.month - 1],
        "iso_week": iso_calendar.week,
        "day_of_month": value.day,
        "day_of_week": iso_calendar.weekday,
        "day_name": _DAY_NAMES[value.weekday()],
        "is_weekend": value.weekday() >= 5,
    }


def _date_range(start_date: date, end_date: date) -> list[date]:
    if end_date < start_date:
        raise WarehouseError("Date dimension range cannot end before it starts.")
    return [
        start_date + timedelta(days=offset) for offset in range((end_date - start_date).days + 1)
    ]


def _issue_hash(issue: DataQualityIssue) -> str:
    payload = {
        "code": issue.code.value,
        "severity": issue.severity.value,
        "reason": issue.reason,
        "source_row_number": issue.source_row_number,
        "source_observation_hash": issue.source_observation_hash,
        "field_name": issue.field_name,
        "record": issue.record,
    }
    serialized = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _redact_configuration_snapshot(value: Any, *, key: str | None = None) -> Any:
    """Make an operational config snapshot useful without persisting credentials."""
    normalized_key = re.sub(r"[^a-z0-9]", "", key.casefold()) if key else ""
    if normalized_key and any(
        sensitive_part in normalized_key for sensitive_part in _SENSITIVE_CONFIGURATION_KEY_PARTS
    ):
        return "***redacted***"
    if isinstance(value, Mapping):
        return {
            str(item_key): _redact_configuration_snapshot(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_redact_configuration_snapshot(item, key=key) for item in value]
    if isinstance(value, str) and (
        value.startswith(("postgresql://", "postgresql+psycopg://"))
        or re.search(r"://[^/\s]+:[^@/\s]+@", value) is not None
    ):
        return "***redacted***"
    return value


class WarehouseLoader:
    """Deploy and populate the dedicated PostgreSQL star schema.

    Values always enter queries as parameters. The source observation hash is
    unique, so a repeat load is a no-op unless a source correction or quality
    state changes the observed content.
    """

    def __init__(self, settings: Settings, *, engine: Engine | None = None) -> None:
        self.settings = settings
        self.engine = engine or create_engine(
            settings.require_database_url(),
            future=True,
            pool_pre_ping=True,
        )

    @property
    def core_schema_path(self) -> Path:
        return self.settings.project_root / "analytics/sql/schema" / CORE_SCHEMA_FILENAME

    @property
    def dashboard_views_path(self) -> Path:
        return self.settings.project_root / "analytics/sql/views" / DASHBOARD_VIEWS_FILENAME

    def close(self) -> None:
        """Release pooled database connections when the pipeline exits."""
        self.engine.dispose()

    def apply_core_schema(self) -> None:
        """Apply the idempotent core schema to the analytics PostgreSQL database."""
        self._apply_sql_file(self.core_schema_path, "core PostgreSQL warehouse schema")

    def apply_dashboard_views(self) -> None:
        """Deploy governed dashboard views after the core schema is available."""
        self._apply_sql_file(self.dashboard_views_path, "dashboard view definitions")

    def _apply_sql_file(self, path: Path, label: str) -> None:
        try:
            sql = path.read_text(encoding="utf-8")
        except OSError as error:
            raise WarehouseError(f"Could not read the {label} file.") from error
        try:
            with self.engine.begin() as connection:
                connection.exec_driver_sql(sql)
        except SQLAlchemyError as error:
            raise WarehouseError(f"Could not apply the {label}.") from error

    def load_validation_result(
        self,
        result: PriceValidationResult,
        *,
        run_id: str,
        source_name: str,
        raw_manifest_path: Path | str | None = None,
        configuration_snapshot: Mapping[str, Any] | None = None,
        ensure_schema: bool = True,
    ) -> WarehouseLoadResult:
        """Upsert one validated run and persist all of its quality findings."""
        self._validate_run_identity(run_id, source_name)
        if ensure_schema:
            self.apply_core_schema()
        self._start_run(
            result,
            run_id=run_id,
            source_name=source_name,
            raw_manifest_path=raw_manifest_path,
            configuration_snapshot=configuration_snapshot,
        )
        try:
            with self.engine.begin() as connection:
                fact_rows_affected = self._load_valid_rows(
                    connection,
                    result,
                    run_id=run_id,
                    source_name=source_name,
                )
                quality_issues_logged = self._load_quality_issues(
                    connection,
                    result.issues,
                    run_id=run_id,
                    source_name=source_name,
                )
                connection.execute(
                    _FINISH_RUN_SQL,
                    {
                        "run_id": run_id,
                        "fact_rows_affected": fact_rows_affected,
                        "quality_issues_logged": quality_issues_logged,
                    },
                )
        except (SQLAlchemyError, WarehouseError) as error:
            self._mark_run_failed(run_id, error)
            if isinstance(error, WarehouseError):
                raise
            raise WarehouseError(
                "Warehouse load failed; inspect controlled database logs."
            ) from error

        return WarehouseLoadResult(
            run_id=run_id,
            source_name=source_name,
            valid_price_rows_received=len(result.valid_rows),
            fact_rows_affected=fact_rows_affected,
            quality_issues_logged=quality_issues_logged,
        )

    def _validate_run_identity(self, run_id: str, source_name: str) -> None:
        if not _SAFE_RUN_ID.fullmatch(run_id):
            raise WarehouseError("run_id must be a safe, non-path pipeline identifier.")
        if not source_name.strip() or len(source_name) > 128:
            raise WarehouseError("source_name must be non-blank and at most 128 characters.")

    def _start_run(
        self,
        result: PriceValidationResult,
        *,
        run_id: str,
        source_name: str,
        raw_manifest_path: Path | str | None,
        configuration_snapshot: Mapping[str, Any] | None,
    ) -> None:
        summary = result.summary
        try:
            freshness_date = (
                date.fromisoformat(summary.data_freshness_date)
                if summary.data_freshness_date
                else None
            )
            configuration_json = json.dumps(
                _redact_configuration_snapshot(configuration_snapshot or {}),
                default=str,
                sort_keys=True,
            )
            with self.engine.begin() as connection:
                connection.execute(
                    _START_RUN_SQL,
                    {
                        "run_id": run_id,
                        "source_name": source_name,
                        "raw_manifest_path": str(raw_manifest_path)
                        if raw_manifest_path is not None
                        else None,
                        "raw_rows_received": summary.raw_rows_received,
                        "valid_rows_loaded": summary.valid_rows_loaded,
                        "invalid_rows_rejected": summary.invalid_rows_rejected,
                        "duplicates_removed": summary.duplicates_removed,
                        "conflicting_observation_count": summary.conflicting_observation_count,
                        "suspicious_price_count": summary.suspicious_price_count,
                        "missing_reporting_date_count": summary.missing_reporting_date_count,
                        "stale_market_count": summary.stale_market_count,
                        "data_freshness_date": freshness_date,
                        "configuration_snapshot": configuration_json,
                    },
                )
        except (SQLAlchemyError, ValueError) as error:
            raise WarehouseError("Could not start the warehouse pipeline run.") from error

    def _load_valid_rows(
        self,
        connection: Connection,
        result: PriceValidationResult,
        *,
        run_id: str,
        source_name: str,
    ) -> int:
        location_cache: dict[tuple[str, str], int] = {}
        market_cache: dict[tuple[int, str], int] = {}
        commodity_cache: dict[tuple[str, str, str], int] = {}
        fact_rows_affected = 0
        rows = result.valid_rows.to_dict(orient="records")
        if rows:
            observed_dates = [_as_date(row.get("market_date")) for row in rows]
            for calendar_date in _date_range(min(observed_dates), max(observed_dates)):
                connection.execute(_UPSERT_DATE_SQL, _date_dimensions(calendar_date))

        for row in rows:
            market_date = _as_date(row.get("market_date"))
            date_values = _date_dimensions(market_date)

            state_name = _as_text(row.get("state"), field_name="state")
            state_normalized = _as_normalized_text(row.get("state_normalized"), field_name="state")
            district_name = _as_text(row.get("district"), field_name="district")
            district_normalized = _as_normalized_text(
                row.get("district_normalized"), field_name="district"
            )
            location_identity = (state_normalized, district_normalized)
            location_key = location_cache.get(location_identity)
            if location_key is None:
                location_key = connection.execute(
                    _UPSERT_LOCATION_SQL,
                    {
                        "state_name": state_name,
                        "state_normalized": state_normalized,
                        "district_name": district_name,
                        "district_normalized": district_normalized,
                    },
                ).scalar_one()
                location_cache[location_identity] = int(location_key)

            market_name = _as_text(row.get("market"), field_name="market")
            market_normalized = _as_normalized_text(
                row.get("market_normalized"), field_name="market"
            )
            market_identity = (location_key, market_normalized)
            market_key = market_cache.get(market_identity)
            if market_key is None:
                market_key = connection.execute(
                    _UPSERT_MARKET_SQL,
                    {
                        "location_key": location_key,
                        "market_name": market_name,
                        "market_normalized": market_normalized,
                    },
                ).scalar_one()
                market_cache[market_identity] = int(market_key)

            commodity_name = _as_text(row.get("commodity"), field_name="commodity")
            commodity_normalized = _as_normalized_text(
                row.get("commodity_normalized"), field_name="commodity"
            )
            variety_name = _as_text(row.get("variety"), field_name="variety", allow_unknown=True)
            variety_normalized = _as_normalized_text(
                row.get("variety_normalized"), field_name="variety", allow_unknown=True
            )
            grade_name = _as_text(row.get("grade"), field_name="grade", allow_unknown=True)
            grade_normalized = _as_normalized_text(
                row.get("grade_normalized"), field_name="grade", allow_unknown=True
            )
            commodity_identity = (commodity_normalized, variety_normalized, grade_normalized)
            commodity_key = commodity_cache.get(commodity_identity)
            if commodity_key is None:
                commodity_key = connection.execute(
                    _UPSERT_COMMODITY_SQL,
                    {
                        "commodity_name": commodity_name,
                        "commodity_normalized": commodity_normalized,
                        "variety_name": variety_name,
                        "variety_normalized": variety_normalized,
                        "grade_name": grade_name,
                        "grade_normalized": grade_normalized,
                    },
                ).scalar_one()
                commodity_cache[commodity_identity] = int(commodity_key)

            fact_result = connection.execute(
                _UPSERT_FACT_SQL,
                {
                    "source_name": source_name,
                    "source_record_id": _nullable_text(row.get("source_record_id")),
                    "source_observation_hash": _as_text(
                        row.get("source_observation_hash"), field_name="source_observation_hash"
                    ),
                    "source_content_hash": _as_text(
                        row.get("source_content_hash"), field_name="source_content_hash"
                    ),
                    "date_key": date_values["date_key"],
                    "market_key": market_key,
                    "commodity_key": commodity_key,
                    "min_price": row.get("min_price"),
                    "max_price": row.get("max_price"),
                    "modal_price": row.get("modal_price"),
                    "price_unit": _as_text(row.get("price_unit"), field_name="price_unit"),
                    "price_spread": row.get("price_spread"),
                    "price_spread_pct": row.get("price_spread_pct"),
                    "quality_status": _as_text(
                        row.get("quality_status"), field_name="quality_status"
                    ),
                    "quality_warning_codes": _nullable_text(row.get("quality_warning_codes")) or "",
                    "run_id": run_id,
                },
            )
            if fact_result.rowcount != 0:
                fact_rows_affected += 1
        return fact_rows_affected

    def _load_quality_issues(
        self,
        connection: Connection,
        issues: list[DataQualityIssue],
        *,
        run_id: str,
        source_name: str,
    ) -> int:
        issues_logged = 0
        for issue in issues:
            record_context = json.dumps(issue.record, default=str, sort_keys=True)
            insert_result = connection.execute(
                _INSERT_QUALITY_ISSUE_SQL,
                {
                    "run_id": run_id,
                    "source_name": source_name,
                    "issue_hash": _issue_hash(issue),
                    "issue_code": issue.code.value,
                    "severity": issue.severity.value,
                    "reason": issue.reason,
                    "source_row_number": issue.source_row_number,
                    "source_observation_hash": issue.source_observation_hash,
                    "field_name": issue.field_name,
                    "record_context": record_context,
                },
            )
            if insert_result.rowcount != 0:
                issues_logged += 1
        return issues_logged

    def _mark_run_failed(self, run_id: str, error: BaseException) -> None:
        """Persist a safe error classification without leaking connection details."""
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    _FAIL_RUN_SQL,
                    {
                        "run_id": run_id,
                        "error_summary": f"Warehouse load failed: {type(error).__name__}",
                    },
                )
        except SQLAlchemyError:
            # The original exception is more actionable to the pipeline caller.
            return
