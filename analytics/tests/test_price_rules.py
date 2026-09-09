from datetime import date
from decimal import Decimal

from farmeasy_mandi_analytics.contracts import QualityIssueCode
from farmeasy_mandi_analytics.validate.price_rules import validate_price_records


def _record(**overrides: str) -> dict[str, str]:
    record = {
        "arrival_date": "08/09/2026",
        "state": " KARNATAKA ",
        "district": "mysuru",
        "market": "Mysuru apmc",
        "commodity": "TOMATO",
        "variety": "local",
        "grade": "FAQ",
        "min_price": "1000",
        "max_price": "2000",
        "modal_price": "1500",
        "_id": "source-1",
    }
    record.update(overrides)
    return record


def _codes(result) -> set[QualityIssueCode]:
    return {issue.code for issue in result.issues}


def test_valid_price_record_is_standardized_and_has_derived_price_metrics() -> None:
    result = validate_price_records(
        [_record()],
        source_name="data_gov_current_mandi",
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 8),
    )

    row = result.valid_rows.iloc[0]
    assert result.summary.raw_rows_received == 1
    assert result.summary.valid_rows_loaded == 1
    assert result.summary.invalid_rows_rejected == 0
    assert row["market_date"] == date(2026, 9, 8)
    assert row["state"] == "Karnataka"
    assert row["market"] == "Mysuru APMC"
    assert row["source_record_id"] == "source-1"
    assert row["min_price"] == Decimal("1000")
    assert row["price_spread"] == Decimal("1000")
    assert row["price_spread_pct"] == Decimal("100")
    assert len(row["source_observation_hash"]) == 64
    assert row["quality_status"] == "valid"


def test_invalid_prices_and_required_values_are_quarantined_with_reasons() -> None:
    invalid_records = [
        _record(state=" "),
        _record(arrival_date="2026/09/08"),
        _record(min_price="not-a-number"),
        _record(min_price="0"),
        _record(min_price="2200", max_price="2000"),
        _record(modal_price="2500"),
    ]

    result = validate_price_records(
        invalid_records,
        source_name="local_official_csv",
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 8),
    )

    assert result.valid_rows.empty
    assert result.summary.invalid_rows_rejected == len(invalid_records)
    assert set(result.rejected_rows["rejection_reason"].str.split(";").explode()) >= {
        "missing_required_value",
        "invalid_date",
        "non_numeric_price",
        "non_positive_price",
        "invalid_price_range",
        "modal_price_outside_range",
    }
    assert _codes(result) >= {
        QualityIssueCode.MISSING_REQUIRED_VALUE,
        QualityIssueCode.INVALID_DATE,
        QualityIssueCode.NON_NUMERIC_PRICE,
        QualityIssueCode.NON_POSITIVE_PRICE,
        QualityIssueCode.INVALID_PRICE_RANGE,
        QualityIssueCode.MODAL_PRICE_OUTSIDE_RANGE,
    }


def test_exact_duplicates_and_conflicting_rows_are_separately_audited() -> None:
    result = validate_price_records(
        [_record(), _record(_id="source-2"), _record(_id="source-3", modal_price="1600")],
        source_name="data_gov_current_mandi",
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 8),
    )

    assert len(result.valid_rows) == 1
    assert result.summary.duplicates_removed == 1
    assert result.summary.conflicting_observation_count == 1
    assert _codes(result) >= {
        QualityIssueCode.DUPLICATE_OBSERVATION,
        QualityIssueCode.CONFLICTING_OBSERVATION,
    }


def test_suspicious_price_changes_remain_valid_but_are_flagged() -> None:
    result = validate_price_records(
        [
            _record(arrival_date="01/09/2026", modal_price="1000"),
            _record(arrival_date="02/09/2026", modal_price="2000"),
        ],
        source_name="data_gov_current_mandi",
        price_unit="INR/quintal",
        suspicious_change_pct=50,
        reference_date=date(2026, 9, 2),
    )

    row = result.valid_rows.sort_values("market_date").iloc[-1]
    assert result.summary.suspicious_price_count == 1
    assert row["previous_modal_price"] == Decimal("1000")
    assert row["modal_price_change_pct"] == Decimal("100")
    assert row["quality_status"] == "suspicious"
    assert "suspicious_price_change" in row["quality_warning_codes"]


def test_missing_reporting_dates_and_stale_markets_are_warning_findings() -> None:
    result = validate_price_records(
        [
            _record(arrival_date="01/09/2026"),
            _record(arrival_date="03/09/2026"),
        ],
        source_name="data_gov_current_mandi",
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 10),
        stale_after_days=3,
    )

    assert result.summary.missing_reporting_date_count == 1
    assert result.summary.stale_market_count == 1
    assert _codes(result) >= {
        QualityIssueCode.MISSING_REPORTING_DATE,
        QualityIssueCode.STALE_MARKET,
    }
    assert "stale_market" in result.valid_rows.iloc[-1]["quality_warning_codes"]


def test_arrival_fields_are_ignored_until_the_optional_module_is_enabled() -> None:
    result = validate_price_records(
        [_record(arrival_quantity="2", arrival_unit="quintals")],
        source_name="local_official_csv",
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 8),
        enable_arrivals=False,
    )

    row = result.valid_rows.iloc[0]
    assert row["arrival_quantity"] is None
    assert row["arrival_unit"] is None
    assert row["arrival_quantity_kg"] is None


def test_enabled_arrivals_are_normalized_and_mixed_units_are_flagged() -> None:
    result = validate_price_records(
        [
            _record(arrival_date="01/09/2026", arrival_quantity="2", arrival_unit="quintals"),
            _record(arrival_date="02/09/2026", arrival_quantity="1", arrival_unit="tonne"),
        ],
        source_name="verified_arrival_source",
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 2),
        suspicious_change_pct=999,
        enable_arrivals=True,
    )

    rows = result.valid_rows.sort_values("market_date")
    assert list(rows["arrival_quantity_kg"]) == [Decimal("200"), Decimal("1000")]
    assert set(rows["arrival_unit"]) == {"quintal", "tonne"}
    assert set(rows["quality_status"]) == {"warning"}
    assert _codes(result) >= {QualityIssueCode.MIXED_ARRIVAL_UNITS}
