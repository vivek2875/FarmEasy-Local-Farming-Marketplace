import json
from datetime import date

import pandas as pd
import pytest

from farmeasy_mandi_analytics.quality.report import (
    DataQualityReportError,
    DataQualityReportWriter,
)
from farmeasy_mandi_analytics.validate.price_rules import validate_price_records


def _record(**overrides: str) -> dict[str, str]:
    record = {
        "arrival_date": "01/09/2026",
        "state": "Karnataka",
        "district": "Mysuru",
        "market": "Mysuru APMC",
        "commodity": "Tomato",
        "min_price": "900",
        "max_price": "1200",
        "modal_price": "1000",
    }
    record.update(overrides)
    return record


def test_quality_report_preserves_summary_quarantine_and_suspicious_evidence(tmp_path) -> None:
    result = validate_price_records(
        [
            _record(),
            _record(arrival_date="02/09/2026", modal_price="2000", max_price="2200"),
            _record(),
        ],
        source_name="data_gov_current_mandi",
        price_unit="INR/quintal",
        suspicious_change_pct=50,
        reference_date=date(2026, 9, 2),
    )

    artifacts = DataQualityReportWriter(tmp_path / "quality").write(
        result,
        run_id="quality-run-1",
        source_name="data_gov_current_mandi",
        source_metadata={
            "request_url": "https://example.test/resource?api-key=must-not-appear",
            "api_key": "must-not-appear",
        },
    )

    payload = json.loads(artifacts.report_path.read_text(encoding="utf-8"))
    rejected = pd.read_csv(artifacts.rejected_records_path)
    suspicious = pd.read_csv(artifacts.suspicious_records_path)
    assert payload["summary"]["raw_rows_received"] == 3
    assert payload["summary"]["valid_rows_loaded"] == 2
    assert payload["summary"]["invalid_rows_rejected"] == 1
    assert payload["summary"]["suspicious_price_count"] == 1
    assert payload["issues_by_code"]["duplicate_observation"] == 1
    assert "must-not-appear" not in artifacts.report_path.read_text(encoding="utf-8")
    assert len(rejected) == 1
    assert len(suspicious) == 1


def test_quality_report_rejects_an_unsafe_run_id(tmp_path) -> None:
    result = validate_price_records(
        [_record()],
        source_name="local_official_csv",
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 1),
    )

    with pytest.raises(DataQualityReportError, match="path separators"):
        DataQualityReportWriter(tmp_path).write(
            result,
            run_id="../unsafe",
            source_name="local_official_csv",
        )
