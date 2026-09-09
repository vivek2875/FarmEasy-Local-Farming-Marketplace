"""Write reviewable data-quality artifacts outside the warehouse.

The warehouse later becomes the long-term audit system, but a portable JSON
summary and CSV evidence files make every local or scheduled run reviewable
even when PostgreSQL is unavailable.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import pandas as pd

from farmeasy_mandi_analytics.contracts import DataQualityIssue
from farmeasy_mandi_analytics.extract.raw_storage import redact_manifest_metadata
from farmeasy_mandi_analytics.validate.price_rules import PriceValidationResult

QUALITY_REPORT_FILENAME = "data_quality_report.json"
REJECTED_RECORDS_FILENAME = "rejected_records.csv"
SUSPICIOUS_RECORDS_FILENAME = "suspicious_price_records.csv"
QUALITY_REPORT_SCHEMA_VERSION = 1

_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class DataQualityReportError(ValueError):
    """Raised when a quality-report artifact cannot be written safely."""


@dataclass(frozen=True, slots=True)
class DataQualityReportArtifacts:
    """Stable locations of one pipeline run's local quality evidence."""

    run_id: str
    report_path: Path
    rejected_records_path: Path
    suspicious_records_path: Path


def _require_safe_run_id(run_id: str) -> str:
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise DataQualityReportError(
            "run_id must contain only letters, numbers, dots, underscores, or hyphens "
            "and must not contain path separators."
        )
    return run_id


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _issue_payload(issue: DataQualityIssue) -> dict[str, Any]:
    return {
        "code": issue.code.value,
        "severity": issue.severity.value,
        "reason": issue.reason,
        "source_row_number": issue.source_row_number,
        "source_observation_hash": issue.source_observation_hash,
        "field_name": issue.field_name,
        "record": issue.record,
    }


def _atomic_write_text(destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.stem}-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(content)
            temporary_name = temporary_file.name
        os.replace(temporary_name, destination)
    except OSError as error:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise DataQualityReportError(f"Could not write quality report {destination}.") from error


def _atomic_write_csv(destination: Path, frame: pd.DataFrame) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.stem}-",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            frame.to_csv(temporary_file, index=False, lineterminator="\n")
            temporary_name = temporary_file.name
        os.replace(temporary_name, destination)
    except (OSError, ValueError) as error:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise DataQualityReportError(
            f"Could not write quality-record CSV {destination}."
        ) from error


class DataQualityReportWriter:
    """Create JSON and CSV quality artifacts for a deterministic pipeline run."""

    def __init__(self, quality_reports_dir: Path | str) -> None:
        self.quality_reports_dir = Path(quality_reports_dir)

    def write(
        self,
        result: PriceValidationResult,
        *,
        run_id: str,
        source_name: str,
        source_metadata: Mapping[str, Any] | None = None,
    ) -> DataQualityReportArtifacts:
        """Persist the summary, quarantined rows, and suspicious-price evidence.

        Re-running this method for the same run ID replaces derived report files
        atomically. Raw receipts stay immutable and are managed separately.
        """
        safe_run_id = _require_safe_run_id(run_id)
        if not source_name.strip():
            raise DataQualityReportError("source_name must not be blank.")

        run_directory = self.quality_reports_dir / safe_run_id
        report_path = run_directory / QUALITY_REPORT_FILENAME
        rejected_path = run_directory / REJECTED_RECORDS_FILENAME
        suspicious_path = run_directory / SUSPICIOUS_RECORDS_FILENAME
        issues = [_issue_payload(issue) for issue in result.issues]
        code_counts = Counter(issue["code"] for issue in issues)
        severity_counts = Counter(issue["severity"] for issue in issues)
        payload = {
            "schema_version": QUALITY_REPORT_SCHEMA_VERSION,
            "run_id": safe_run_id,
            "source_name": source_name,
            "summary": asdict(result.summary),
            "issue_count": len(issues),
            "issues_by_code": dict(sorted(code_counts.items())),
            "issues_by_severity": dict(sorted(severity_counts.items())),
            "source_metadata": redact_manifest_metadata(source_metadata),
            "issues": issues,
        }
        serialized = (
            json.dumps(
                payload,
                default=_json_default,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        _atomic_write_text(report_path, serialized)
        _atomic_write_csv(rejected_path, result.rejected_rows)
        suspicious_rows = result.valid_rows[
            result.valid_rows["quality_warning_codes"].str.contains(
                "suspicious_price_change", na=False
            )
        ]
        _atomic_write_csv(suspicious_path, suspicious_rows)
        return DataQualityReportArtifacts(
            run_id=safe_run_id,
            report_path=report_path,
            rejected_records_path=rejected_path,
            suspicious_records_path=suspicious_path,
        )


def write_data_quality_report(
    quality_reports_dir: Path | str,
    result: PriceValidationResult,
    *,
    run_id: str,
    source_name: str,
    source_metadata: Mapping[str, Any] | None = None,
) -> DataQualityReportArtifacts:
    """Convenience wrapper for writing a run's quality artifacts."""
    return DataQualityReportWriter(quality_reports_dir).write(
        result,
        run_id=run_id,
        source_name=source_name,
        source_metadata=source_metadata,
    )
