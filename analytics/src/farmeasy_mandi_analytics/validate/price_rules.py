"""Data-quality validation for official mandi-price observations."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any

import pandas as pd

from farmeasy_mandi_analytics.contracts import (
    REQUIRED_PRICE_FIELDS,
    DataQualityIssue,
    DataQualitySummary,
    QualityIssueCode,
    QualitySeverity,
)

from .standardize import (
    NameStandardizer,
    collapse_whitespace,
    is_missing_text,
    normalize_name_key,
)

SOURCE_FIELD_MAP = {
    "market_date": ("market_date", "arrival_date", "Arrival_Date"),
    "state": ("state", "State"),
    "district": ("district", "District"),
    "market": ("market", "Market"),
    "commodity": ("commodity", "Commodity"),
    "variety": ("variety", "Variety"),
    "grade": ("grade", "Grade"),
    "min_price": ("min_price", "Min_x0020_Price"),
    "max_price": ("max_price", "Max_x0020_Price"),
    "modal_price": ("modal_price", "Modal_x0020_Price"),
    "arrival_quantity": ("arrival_quantity", "Arrival_Quantity"),
    "arrival_unit": ("arrival_unit", "Arrival_Unit"),
    "source_record_id": ("source_record_id", "_id", "id"),
}
NAME_FIELDS = ("state", "district", "market", "commodity", "variety", "grade")
PRICE_FIELDS = ("min_price", "max_price", "modal_price")
NATURAL_GRAIN_FIELDS = (
    "source_name",
    "market_date",
    "state_normalized",
    "district_normalized",
    "market_normalized",
    "commodity_normalized",
    "variety_normalized",
    "grade_normalized",
)
ARRIVAL_UNIT_ALIASES = {
    "kg": ("kg", Decimal("1")),
    "kilogram": ("kg", Decimal("1")),
    "kilograms": ("kg", Decimal("1")),
    "quintal": ("quintal", Decimal("100")),
    "quintals": ("quintal", Decimal("100")),
    "qtl": ("quintal", Decimal("100")),
    "tonne": ("tonne", Decimal("1000")),
    "tonnes": ("tonne", Decimal("1000")),
    "metric tonne": ("tonne", Decimal("1000")),
    "metric tonnes": ("tonne", Decimal("1000")),
    "mt": ("tonne", Decimal("1000")),
}


@dataclass(slots=True)
class PriceValidationResult:
    """Auditable outcome of validation and basic price transformation."""

    raw_rows: pd.DataFrame
    valid_rows: pd.DataFrame
    rejected_rows: pd.DataFrame
    issues: list[DataQualityIssue]
    summary: DataQualitySummary


def _parse_market_date(value: Any) -> date | None:
    if is_missing_text(value):
        return None
    text = str(value).strip()
    for date_format in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    return None


def _parse_decimal(value: Any) -> Decimal | None:
    if is_missing_text(value):
        return None
    try:
        parsed = Decimal(str(value).strip().replace(",", ""))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _content_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(serialized.encode("utf-8")).hexdigest()


def _source_column(frame: pd.DataFrame, field_name: str) -> pd.Series:
    for source_field in SOURCE_FIELD_MAP[field_name]:
        if source_field in frame.columns:
            return frame[source_field]
    return pd.Series([None] * len(frame), index=frame.index, dtype="object")


def _row_source_record(
    records: list[dict[str, Any]], position: int | None
) -> dict[str, Any] | None:
    return dict(records[position]) if position is not None else None


def _issue_reason(code: QualityIssueCode, field_name: str | None = None) -> str:
    descriptions = {
        QualityIssueCode.MISSING_REQUIRED_VALUE: (
            "A required source value is missing after cleanup."
        ),
        QualityIssueCode.INVALID_DATE: (
            "The market date does not match an accepted source date format."
        ),
        QualityIssueCode.NON_NUMERIC_PRICE: "The price cannot be parsed as a finite decimal.",
        QualityIssueCode.NON_POSITIVE_PRICE: "A market price must be greater than zero.",
        QualityIssueCode.INVALID_PRICE_RANGE: "Minimum price is greater than maximum price.",
        QualityIssueCode.MODAL_PRICE_OUTSIDE_RANGE: (
            "Modal price is outside the inclusive min/max range."
        ),
        QualityIssueCode.INVALID_ARRIVAL_UNIT: "Arrival quantity has no supported, verified unit.",
        QualityIssueCode.INVALID_ARRIVAL_QUANTITY: (
            "Arrival quantity is missing, non-numeric, or non-positive."
        ),
    }
    prefix = descriptions.get(code, code.replace("_", " ").capitalize())
    return f"{prefix} Field: {field_name}." if field_name else prefix


def _build_working_frame(
    records: list[dict[str, Any]],
    *,
    source_name: str,
    price_unit: str,
    standardizer: NameStandardizer,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw_frame = pd.DataFrame.from_records(records)
    working = pd.DataFrame(index=raw_frame.index)
    working["source_row_number"] = range(1, len(raw_frame) + 1)
    working["source_name"] = source_name
    working["price_unit"] = price_unit

    for field_name in SOURCE_FIELD_MAP:
        raw_values = _source_column(raw_frame, field_name)
        working[f"raw_{field_name}"] = raw_values

    for field_name in NAME_FIELDS:
        values = [
            standardizer.standardize(field_name, value) for value in working[f"raw_{field_name}"]
        ]
        working[field_name] = [value[0] for value in values]
        working[f"{field_name}_normalized"] = [value[1] for value in values]

    working["source_record_id"] = [
        collapse_whitespace(value) for value in working["raw_source_record_id"]
    ]

    working["market_date"] = [_parse_market_date(value) for value in working["raw_market_date"]]
    for field_name in PRICE_FIELDS:
        working[field_name] = [_parse_decimal(value) for value in working[f"raw_{field_name}"]]

    working["arrival_quantity"] = [
        _parse_decimal(value) for value in working["raw_arrival_quantity"]
    ]
    working["arrival_unit"] = [normalize_name_key(value) for value in working["raw_arrival_unit"]]
    working["arrival_quantity_kg"] = None
    working["source_observation_hash"] = None
    working["source_content_hash"] = None
    working["price_spread"] = None
    working["price_spread_pct"] = None
    working["previous_modal_price"] = None
    working["modal_price_change_pct"] = None
    return raw_frame, working


def validate_price_records(
    records: Iterable[Mapping[str, Any]],
    *,
    source_name: str,
    price_unit: str,
    standardizer: NameStandardizer | None = None,
    reference_date: date | None = None,
    stale_after_days: int = 3,
    suspicious_change_pct: float = 75.0,
    enable_arrivals: bool = False,
) -> PriceValidationResult:
    """Validate and standardize raw price records without silently discarding evidence.

    Errors quarantine a row in ``rejected_rows``; warnings retain the row in
    ``valid_rows`` with quality-warning metadata. All findings are returned for
    persistence in the later ``data_quality_log`` warehouse table.
    """
    if not source_name.strip():
        raise ValueError("source_name must not be blank.")
    if not price_unit.strip():
        raise ValueError("price_unit must not be blank.")
    if stale_after_days < 1:
        raise ValueError("stale_after_days must be at least 1.")
    if suspicious_change_pct < 0:
        raise ValueError("suspicious_change_pct must not be negative.")

    source_records = [dict(record) for record in records]
    standardizer = standardizer or NameStandardizer()
    raw_frame, working = _build_working_frame(
        source_records,
        source_name=source_name,
        price_unit=price_unit,
        standardizer=standardizer,
    )
    summary = DataQualitySummary(raw_rows_received=len(working))
    summary.pipeline_executed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    issues: list[DataQualityIssue] = []
    rejected_positions: set[int] = set()
    rejection_reasons: dict[int, list[str]] = defaultdict(list)
    warning_codes: dict[int, set[str]] = defaultdict(set)

    def add_issue(
        code: QualityIssueCode,
        severity: QualitySeverity,
        reason: str,
        *,
        position: int | None = None,
        field_name: str | None = None,
        source_hash: str | None = None,
        record: dict[str, Any] | None = None,
    ) -> None:
        issues.append(
            DataQualityIssue(
                code=code,
                severity=severity,
                reason=reason,
                source_row_number=position + 1 if position is not None else None,
                source_observation_hash=source_hash,
                field_name=field_name,
                record=record
                if record is not None
                else _row_source_record(source_records, position),
            )
        )
        if position is None:
            return
        if severity == QualitySeverity.ERROR:
            rejected_positions.add(position)
            rejection_reasons[position].append(code.value)
        elif severity == QualitySeverity.WARNING:
            warning_codes[position].add(code.value)

    for field_name in SOURCE_FIELD_MAP:
        raw_column = working[f"raw_{field_name}"]
        missing_mask = raw_column.map(is_missing_text)
        summary.missing_value_counts[field_name] = int(missing_mask.sum())
        if field_name in REQUIRED_PRICE_FIELDS:
            for position in working.index[missing_mask]:
                add_issue(
                    QualityIssueCode.MISSING_REQUIRED_VALUE,
                    QualitySeverity.ERROR,
                    _issue_reason(QualityIssueCode.MISSING_REQUIRED_VALUE, field_name),
                    position=int(position),
                    field_name=field_name,
                )

    for position, value in enumerate(working["raw_market_date"]):
        if not is_missing_text(value) and working.at[position, "market_date"] is None:
            add_issue(
                QualityIssueCode.INVALID_DATE,
                QualitySeverity.ERROR,
                _issue_reason(QualityIssueCode.INVALID_DATE, "market_date"),
                position=position,
                field_name="market_date",
            )

    for field_name in PRICE_FIELDS:
        for position, raw_value in enumerate(working[f"raw_{field_name}"]):
            parsed = working.at[position, field_name]
            if is_missing_text(raw_value):
                continue
            if parsed is None:
                add_issue(
                    QualityIssueCode.NON_NUMERIC_PRICE,
                    QualitySeverity.ERROR,
                    _issue_reason(QualityIssueCode.NON_NUMERIC_PRICE, field_name),
                    position=position,
                    field_name=field_name,
                )
            elif parsed <= 0:
                add_issue(
                    QualityIssueCode.NON_POSITIVE_PRICE,
                    QualitySeverity.ERROR,
                    _issue_reason(QualityIssueCode.NON_POSITIVE_PRICE, field_name),
                    position=position,
                    field_name=field_name,
                )

    for position in working.index:
        min_price = working.at[position, "min_price"]
        max_price = working.at[position, "max_price"]
        modal_price = working.at[position, "modal_price"]
        if min_price is not None and max_price is not None and min_price > max_price:
            add_issue(
                QualityIssueCode.INVALID_PRICE_RANGE,
                QualitySeverity.ERROR,
                _issue_reason(QualityIssueCode.INVALID_PRICE_RANGE),
                position=int(position),
            )
        if (
            min_price is not None
            and max_price is not None
            and modal_price is not None
            and not (min_price <= modal_price <= max_price)
        ):
            add_issue(
                QualityIssueCode.MODAL_PRICE_OUTSIDE_RANGE,
                QualitySeverity.ERROR,
                _issue_reason(QualityIssueCode.MODAL_PRICE_OUTSIDE_RANGE),
                position=int(position),
            )

    _validate_arrivals(working, add_issue, enable_arrivals=enable_arrivals)

    for position in working.index:
        if int(position) in rejected_positions:
            continue
        grain = {
            field_name: working.at[position, field_name] for field_name in NATURAL_GRAIN_FIELDS
        }
        observation_hash = _content_hash(grain)
        content = {
            **grain,
            "min_price": working.at[position, "min_price"],
            "max_price": working.at[position, "max_price"],
            "modal_price": working.at[position, "modal_price"],
            "price_unit": price_unit,
            "arrival_quantity": working.at[position, "arrival_quantity"],
            "arrival_unit": working.at[position, "arrival_unit"],
        }
        working.at[position, "source_observation_hash"] = observation_hash
        working.at[position, "source_content_hash"] = _content_hash(content)

    seen_observations: dict[str, int] = {}
    for position in working.index:
        position = int(position)
        if position in rejected_positions:
            continue
        observation_hash = str(working.at[position, "source_observation_hash"])
        first_position = seen_observations.get(observation_hash)
        if first_position is None:
            seen_observations[observation_hash] = position
            continue
        same_content = (
            working.at[first_position, "source_content_hash"]
            == working.at[position, "source_content_hash"]
        )
        code = (
            QualityIssueCode.DUPLICATE_OBSERVATION
            if same_content
            else QualityIssueCode.CONFLICTING_OBSERVATION
        )
        add_issue(
            code,
            QualitySeverity.ERROR,
            "The source returned another record with the same observation grain; "
            "the first received row was retained for this run.",
            position=position,
            source_hash=observation_hash,
        )
        if code == QualityIssueCode.DUPLICATE_OBSERVATION:
            summary.duplicates_removed += 1
        else:
            summary.conflicting_observation_count += 1

    valid_positions = [
        position for position in working.index if int(position) not in rejected_positions
    ]
    valid_rows = working.loc[valid_positions].copy()
    rejected_rows = working.loc[sorted(rejected_positions)].copy()
    rejected_rows["rejection_reason"] = [
        ";".join(rejection_reasons[int(position)]) for position in rejected_rows.index
    ]

    _add_price_spreads(valid_rows)
    _add_suspicious_price_flags(
        valid_rows,
        add_issue,
        warning_codes,
        suspicious_change_pct=suspicious_change_pct,
    )
    _add_reporting_gap_and_stale_flags(
        valid_rows,
        add_issue,
        reference_date=reference_date or datetime.now(UTC).date(),
        stale_after_days=stale_after_days,
    )

    valid_rows["quality_warning_codes"] = [
        ";".join(sorted(warning_codes[int(position)])) for position in valid_rows.index
    ]
    valid_rows["quality_status"] = valid_rows["quality_warning_codes"].map(
        _quality_status_from_warning_codes
    )
    summary.valid_rows_loaded = len(valid_rows)
    summary.invalid_rows_rejected = len(rejected_rows)
    summary.suspicious_price_count = sum(
        issue.code == QualityIssueCode.SUSPICIOUS_PRICE_CHANGE for issue in issues
    )
    summary.missing_reporting_date_count = sum(
        issue.code == QualityIssueCode.MISSING_REPORTING_DATE for issue in issues
    )
    summary.stale_market_count = sum(
        issue.code == QualityIssueCode.STALE_MARKET for issue in issues
    )
    if not valid_rows.empty:
        summary.data_freshness_date = max(valid_rows["market_date"]).isoformat()

    return PriceValidationResult(
        raw_rows=raw_frame,
        valid_rows=valid_rows.reset_index(drop=True),
        rejected_rows=rejected_rows.reset_index(drop=True),
        issues=issues,
        summary=summary,
    )


def _validate_arrivals(
    working: pd.DataFrame,
    add_issue: Any,
    *,
    enable_arrivals: bool,
) -> None:
    """Validate optional arrival values without sacrificing usable price rows."""
    if not enable_arrivals:
        # The current primary price resource contains no verified quantity/unit
        # fields. Keep raw values for traceability but never treat them as supply.
        working["arrival_quantity"] = None
        working["arrival_unit"] = None
        working["arrival_quantity_kg"] = None
        return

    valid_units: set[str] = set()
    for position in working.index:
        raw_quantity = working.at[position, "raw_arrival_quantity"]
        raw_unit = working.at[position, "raw_arrival_unit"]
        has_quantity = not is_missing_text(raw_quantity)
        has_unit = not is_missing_text(raw_unit)
        if not has_quantity and not has_unit:
            continue

        quantity = working.at[position, "arrival_quantity"]
        if quantity is None or quantity <= 0:
            add_issue(
                QualityIssueCode.INVALID_ARRIVAL_QUANTITY,
                QualitySeverity.WARNING,
                _issue_reason(QualityIssueCode.INVALID_ARRIVAL_QUANTITY, "arrival_quantity"),
                position=int(position),
                field_name="arrival_quantity",
            )
            working.at[position, "arrival_quantity"] = None
            working.at[position, "arrival_unit"] = None
            continue

        normalized_unit = normalize_name_key(raw_unit)
        conversion = ARRIVAL_UNIT_ALIASES.get(normalized_unit or "")
        if conversion is None:
            add_issue(
                QualityIssueCode.INVALID_ARRIVAL_UNIT,
                QualitySeverity.WARNING,
                _issue_reason(QualityIssueCode.INVALID_ARRIVAL_UNIT, "arrival_unit"),
                position=int(position),
                field_name="arrival_unit",
            )
            working.at[position, "arrival_quantity"] = None
            working.at[position, "arrival_unit"] = None
            continue

        canonical_unit, kilogram_factor = conversion
        working.at[position, "arrival_unit"] = canonical_unit
        working.at[position, "arrival_quantity_kg"] = quantity * kilogram_factor
        valid_units.add(canonical_unit)

    if enable_arrivals and len(valid_units) > 1:
        for position in working.index:
            if working.at[position, "arrival_unit"] is not None:
                add_issue(
                    QualityIssueCode.MIXED_ARRIVAL_UNITS,
                    QualitySeverity.WARNING,
                    "Multiple verified arrival units were received; use normalized kilograms "
                    "for any future supply aggregation.",
                    position=int(position),
                    field_name="arrival_unit",
                )


def _add_price_spreads(valid_rows: pd.DataFrame) -> None:
    for position in valid_rows.index:
        min_price = valid_rows.at[position, "min_price"]
        max_price = valid_rows.at[position, "max_price"]
        spread = max_price - min_price
        valid_rows.at[position, "price_spread"] = spread
        valid_rows.at[position, "price_spread_pct"] = (spread / min_price) * Decimal("100")


def _add_suspicious_price_flags(
    valid_rows: pd.DataFrame,
    add_issue: Any,
    warning_codes: dict[int, set[str]],
    *,
    suspicious_change_pct: float,
) -> None:
    group_columns = [
        "state_normalized",
        "district_normalized",
        "market_normalized",
        "commodity_normalized",
        "variety_normalized",
        "grade_normalized",
    ]
    for _, group in valid_rows.groupby(group_columns, dropna=False):
        previous_price: Decimal | None = None
        for position, row in group.sort_values("market_date").iterrows():
            current_price = row["modal_price"]
            if previous_price is not None:
                change_pct = ((current_price - previous_price) / previous_price) * Decimal("100")
                valid_rows.at[position, "previous_modal_price"] = previous_price
                valid_rows.at[position, "modal_price_change_pct"] = change_pct
                if abs(change_pct) > Decimal(str(suspicious_change_pct)):
                    add_issue(
                        QualityIssueCode.SUSPICIOUS_PRICE_CHANGE,
                        QualitySeverity.WARNING,
                        "Modal price changed beyond the configured suspicious-change threshold "
                        f"({suspicious_change_pct}%) from the prior market observation.",
                        position=int(position),
                        source_hash=valid_rows.at[position, "source_observation_hash"],
                    )
                    warning_codes[int(position)].add(QualityIssueCode.SUSPICIOUS_PRICE_CHANGE.value)
            previous_price = current_price


def _quality_status_from_warning_codes(value: str) -> str:
    if not value:
        return "valid"
    warning_codes = set(value.split(";"))
    if QualityIssueCode.SUSPICIOUS_PRICE_CHANGE.value in warning_codes:
        return "suspicious"
    return "warning"


def _add_reporting_gap_and_stale_flags(
    valid_rows: pd.DataFrame,
    add_issue: Any,
    *,
    reference_date: date,
    stale_after_days: int,
) -> None:
    market_columns = ["state_normalized", "district_normalized", "market_normalized"]
    for _group_key, group in valid_rows.groupby(market_columns, dropna=False):
        latest_position = group["market_date"].idxmax()
        latest_date = valid_rows.at[latest_position, "market_date"]
        age_days = (reference_date - latest_date).days
        if age_days > stale_after_days:
            stale_reason = (
                f"Market has no observation within {stale_after_days} day(s); "
                f"latest is {latest_date}."
            )
            add_issue(
                QualityIssueCode.STALE_MARKET,
                QualitySeverity.WARNING,
                stale_reason,
                position=int(latest_position),
                source_hash=valid_rows.at[latest_position, "source_observation_hash"],
            )

    gap_columns = [
        "state_normalized",
        "district_normalized",
        "market_normalized",
        "commodity_normalized",
        "variety_normalized",
        "grade_normalized",
    ]
    for group_key, group in valid_rows.groupby(gap_columns, dropna=False):
        dates = sorted(group["market_date"])
        if len(dates) < 2:
            continue
        observed_dates = set(dates)
        for missing_timestamp in pd.date_range(dates[0], dates[-1], freq="D"):
            missing_date = missing_timestamp.date()
            if missing_date not in observed_dates:
                location_label = ", ".join(str(value) for value in group_key[:3])
                gap_reason = (
                    f"No market report was observed for {missing_date} in {location_label}; "
                    "this is a reporting gap, not zero supply."
                )
                add_issue(
                    QualityIssueCode.MISSING_REPORTING_DATE,
                    QualitySeverity.WARNING,
                    gap_reason,
                    record={
                        "market_date": missing_date.isoformat(),
                        "state_normalized": group_key[0],
                        "district_normalized": group_key[1],
                        "market_normalized": group_key[2],
                        "commodity_normalized": group_key[3],
                    },
                )
