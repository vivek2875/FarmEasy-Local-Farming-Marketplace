"""Command-line entry points for diagnostics and source extraction."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from .config import ConfigurationError, Settings, load_settings
from .extract.csv_source import CsvSource, CsvSourceError
from .extract.data_gov import DataGovClient, DataGovExtractionError
from .extract.raw_storage import RawReceiptError, RawReceiptStore
from .load.warehouse import WarehouseError, WarehouseLoader, WarehouseLoadResult
from .quality.report import DataQualityReportError, DataQualityReportWriter
from .storage.processed import ProcessedDatasetError, ProcessedDatasetWriter
from .transform.mandi_prices import transform_price_records

DATA_GOV_SOURCE_NAME = "data_gov_current_mandi"


@dataclass(frozen=True, slots=True)
class _ValidationArtifacts:
    run_id: str
    source_name: str
    validation: Any
    raw_manifest: str
    processed_dataset: str
    quality_report: str


@dataclass(frozen=True, slots=True)
class _ApiValidationArtifacts:
    validation_artifacts: _ValidationArtifacts
    pages_preserved: int
    filters: dict[str, str]


def _default_run_id() -> str:
    return f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}"


def _add_source_filters(parser: argparse.ArgumentParser) -> None:
    for field_name in ("state", "district", "market", "commodity", "variety", "grade"):
        parser.add_argument(f"--{field_name.replace('_', '-')}", dest=field_name)


def _filters_from_args(args: argparse.Namespace) -> dict[str, str]:
    return {
        field_name: value
        for field_name in ("state", "district", "market", "commodity", "variety", "grade")
        if (value := getattr(args, field_name, None))
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="farmeasy-mandi",
        description="FarmEasy Mandi Price and Supply Intelligence pipeline.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("show-config", help="Print a redacted configuration summary.")
    subcommands.add_parser(
        "deploy-views",
        help="Create or replace the dashboard-ready PostgreSQL views.",
    )

    api_help = (
        "Download and preserve raw Data.gov.in API pages; " + "no transformation or loading occurs."
    )
    api_parser = subcommands.add_parser(
        "extract-api",
        help=api_help,
    )
    api_parser.add_argument("--run-id", default=None, help="Safe pipeline run identifier.")
    api_parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Optional positive safety limit for an intentionally partial extraction.",
    )
    _add_source_filters(api_parser)

    csv_help = (
        "Preserve and read a local official CSV fallback; " + "no transformation or loading occurs."
    )
    csv_parser = subcommands.add_parser(
        "extract-csv",
        help=csv_help,
    )
    csv_parser.add_argument("path", help="Path to a CSV downloaded from the official source.")
    csv_parser.add_argument("--run-id", default=None, help="Safe pipeline run identifier.")
    csv_parser.add_argument(
        "--official-source-url",
        default=None,
        help="Official catalog/resource URL used to obtain the file, recorded in the manifest.",
    )

    validate_csv_parser = subcommands.add_parser(
        "validate-csv",
        help="Preserve, validate, and transform a local official CSV without database loading.",
    )
    validate_csv_parser.add_argument(
        "path", help="Path to a CSV downloaded from the official source."
    )
    validate_csv_parser.add_argument("--run-id", default=None, help="Safe pipeline run identifier.")
    validate_csv_parser.add_argument(
        "--official-source-url",
        default=None,
        help="Official catalog/resource URL used to obtain the file, recorded in artifacts.",
    )
    validate_csv_parser.add_argument(
        "--reference-date",
        default=None,
        help="Optional YYYY-MM-DD date for deterministic freshness and gap checks.",
    )

    load_csv_parser = subcommands.add_parser(
        "load-csv",
        help="Preserve, validate, and load a local official CSV into PostgreSQL.",
    )
    load_csv_parser.add_argument("path", help="Path to a CSV downloaded from the official source.")
    load_csv_parser.add_argument("--run-id", default=None, help="Safe pipeline run identifier.")
    load_csv_parser.add_argument(
        "--official-source-url",
        default=None,
        help="Official catalog/resource URL used to obtain the file, recorded in artifacts.",
    )
    load_csv_parser.add_argument(
        "--reference-date",
        default=None,
        help="Optional YYYY-MM-DD date for deterministic freshness and gap checks.",
    )

    validate_api_parser = subcommands.add_parser(
        "validate-api",
        help="Preserve, validate, and transform all matching Data.gov.in API pages.",
    )
    validate_api_parser.add_argument("--run-id", default=None, help="Safe pipeline run identifier.")
    validate_api_parser.add_argument(
        "--reference-date",
        default=None,
        help="Optional YYYY-MM-DD date for deterministic freshness and gap checks.",
    )
    _add_source_filters(validate_api_parser)

    load_api_parser = subcommands.add_parser(
        "load-api",
        help="Preserve, validate, and load all matching Data.gov.in API pages into PostgreSQL.",
    )
    load_api_parser.add_argument("--run-id", default=None, help="Safe pipeline run identifier.")
    load_api_parser.add_argument(
        "--reference-date",
        default=None,
        help="Optional YYYY-MM-DD date for deterministic freshness and gap checks.",
    )
    _add_source_filters(load_api_parser)
    return parser


def _extract_api(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    if args.max_pages is not None and args.max_pages < 1:
        raise ValueError("--max-pages must be at least 1 when supplied.")

    run_id = args.run_id or _default_run_id()
    store = RawReceiptStore(settings.raw_dir)
    filters = _filters_from_args(args)
    page_count = 0
    record_count = 0
    truncated = False

    with DataGovClient(settings) as client:
        for page in client.iter_pages(filters=filters or None):
            store.store_bytes(
                page.raw_bytes,
                run_id=run_id,
                source_name=DATA_GOV_SOURCE_NAME,
                suffix=".json",
                content_type=page.content_type,
                captured_at=page.received_at,
                metadata={
                    "source_type": "data_gov_in_api",
                    "resource_id": settings.data_gov_resource_id,
                    "resource_url": f"{settings.data_gov_api_url}/{settings.data_gov_resource_id}",
                    "page_offset": page.offset,
                    "page_limit": page.limit,
                    "returned_record_count": page.record_count,
                    "source_reported_total": page.total,
                    "response_status": page.status_code,
                    "filters": filters,
                },
            )
            page_count += 1
            record_count += page.record_count
            if args.max_pages is not None and page_count >= args.max_pages:
                truncated = True
                break

    return {
        "run_id": run_id,
        "source": DATA_GOV_SOURCE_NAME,
        "pages_preserved": page_count,
        "records_received": record_count,
        "filters": filters,
        "truncated": truncated,
        "manifest": str(store.manifest_path_for(run_id)),
    }


def _extract_csv(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    run_id = args.run_id or _default_run_id()
    store = RawReceiptStore(settings.raw_dir)
    source = CsvSource(args.path, source_name="local_official_csv")
    result = source.read(
        raw_store=store,
        run_id=run_id,
        metadata={
            "source_type": "local_official_csv",
            "official_source_url": args.official_source_url,
        },
    )
    return {
        "run_id": run_id,
        "source": result.source_name,
        "records_received": len(result.records),
        "headers": result.headers,
        "manifest": str(store.manifest_path_for(run_id)),
    }


def _parse_reference_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("--reference-date must use YYYY-MM-DD format.") from error


def _run_csv_validation(settings: Settings, args: argparse.Namespace) -> _ValidationArtifacts:
    run_id = args.run_id or _default_run_id()
    store = RawReceiptStore(settings.raw_dir)
    source = CsvSource(args.path, source_name="local_official_csv")
    extraction = source.read(
        raw_store=store,
        run_id=run_id,
        metadata={
            "source_type": "local_official_csv",
            "official_source_url": args.official_source_url,
        },
    )
    validation = transform_price_records(
        extraction.records,
        settings=settings,
        source_name=extraction.source_name,
        reference_date=_parse_reference_date(args.reference_date),
    )
    quality_artifacts = DataQualityReportWriter(settings.quality_reports_dir).write(
        validation,
        run_id=run_id,
        source_name=extraction.source_name,
        source_metadata={
            "official_source_url": args.official_source_url,
            "raw_receipt_sha256": (
                extraction.raw_receipt.sha256 if extraction.raw_receipt is not None else None
            ),
            "raw_manifest": str(store.manifest_path_for(run_id)),
        },
    )
    processed_artifacts = ProcessedDatasetWriter(settings.processed_dir).write_validated_prices(
        validation.valid_rows,
        run_id=run_id,
    )
    return _ValidationArtifacts(
        run_id=run_id,
        source_name=extraction.source_name,
        validation=validation,
        raw_manifest=str(store.manifest_path_for(run_id)),
        processed_dataset=str(processed_artifacts.validated_prices_path),
        quality_report=str(quality_artifacts.report_path),
    )


def _run_api_validation(settings: Settings, args: argparse.Namespace) -> _ApiValidationArtifacts:
    run_id = args.run_id or _default_run_id()
    store = RawReceiptStore(settings.raw_dir)
    filters = _filters_from_args(args)
    records: list[dict[str, Any]] = []
    pages_preserved = 0

    with DataGovClient(settings) as client:
        for page in client.iter_pages(filters=filters or None):
            store.store_bytes(
                page.raw_bytes,
                run_id=run_id,
                source_name=DATA_GOV_SOURCE_NAME,
                suffix=".json",
                content_type=page.content_type,
                captured_at=page.received_at,
                metadata={
                    "source_type": "data_gov_in_api",
                    "resource_id": settings.data_gov_resource_id,
                    "resource_url": f"{settings.data_gov_api_url}/{settings.data_gov_resource_id}",
                    "page_offset": page.offset,
                    "page_limit": page.limit,
                    "returned_record_count": page.record_count,
                    "source_reported_total": page.total,
                    "response_status": page.status_code,
                    "filters": filters,
                },
            )
            records.extend(page.records)
            pages_preserved += 1

    validation = transform_price_records(
        records,
        settings=settings,
        source_name=DATA_GOV_SOURCE_NAME,
        reference_date=_parse_reference_date(args.reference_date),
    )
    raw_manifest = str(store.manifest_path_for(run_id))
    quality_artifacts = DataQualityReportWriter(settings.quality_reports_dir).write(
        validation,
        run_id=run_id,
        source_name=DATA_GOV_SOURCE_NAME,
        source_metadata={
            "resource_id": settings.data_gov_resource_id,
            "official_resource_url": f"{settings.data_gov_api_url}/{settings.data_gov_resource_id}",
            "filters": filters,
            "pages_preserved": pages_preserved,
            "raw_manifest": raw_manifest,
        },
    )
    processed_artifacts = ProcessedDatasetWriter(settings.processed_dir).write_validated_prices(
        validation.valid_rows,
        run_id=run_id,
    )
    return _ApiValidationArtifacts(
        validation_artifacts=_ValidationArtifacts(
            run_id=run_id,
            source_name=DATA_GOV_SOURCE_NAME,
            validation=validation,
            raw_manifest=raw_manifest,
            processed_dataset=str(processed_artifacts.validated_prices_path),
            quality_report=str(quality_artifacts.report_path),
        ),
        pages_preserved=pages_preserved,
        filters=filters,
    )


def _validation_payload(artifacts: _ValidationArtifacts) -> dict[str, Any]:
    summary = artifacts.validation.summary
    return {
        "run_id": artifacts.run_id,
        "source": artifacts.source_name,
        "records_received": summary.raw_rows_received,
        "valid_rows": summary.valid_rows_loaded,
        "invalid_rows": summary.invalid_rows_rejected,
        "duplicates_removed": summary.duplicates_removed,
        "suspicious_price_rows": summary.suspicious_price_count,
        "data_freshness_date": summary.data_freshness_date,
        "raw_manifest": artifacts.raw_manifest,
        "processed_dataset": artifacts.processed_dataset,
        "quality_report": artifacts.quality_report,
    }


def _validate_csv(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    return _validation_payload(_run_csv_validation(settings, args))


def _api_validation_payload(artifacts: _ApiValidationArtifacts) -> dict[str, Any]:
    return {
        **_validation_payload(artifacts.validation_artifacts),
        "pages_preserved": artifacts.pages_preserved,
        "filters": artifacts.filters,
    }


def _validate_api(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    return _api_validation_payload(_run_api_validation(settings, args))


def _load_validation_to_warehouse(
    settings: Settings,
    artifacts: _ValidationArtifacts,
) -> WarehouseLoadResult:
    loader = WarehouseLoader(settings)
    try:
        return loader.load_validation_result(
            artifacts.validation,
            run_id=artifacts.run_id,
            source_name=artifacts.source_name,
            raw_manifest_path=artifacts.raw_manifest,
            configuration_snapshot=settings.redacted(),
        )
    finally:
        loader.close()


def _load_csv(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    # Fail before receiving a new source file if the requested warehouse target
    # is not configured. ``validate-csv`` remains available for offline review.
    settings.require_database_url()
    artifacts = _run_csv_validation(settings, args)
    warehouse_result = _load_validation_to_warehouse(settings, artifacts)

    return {
        **_validation_payload(artifacts),
        "warehouse": {
            "valid_price_rows_received": warehouse_result.valid_price_rows_received,
            "fact_rows_affected": warehouse_result.fact_rows_affected,
            "quality_issues_logged": warehouse_result.quality_issues_logged,
        },
    }


def _load_api(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    settings.require_database_url()
    api_artifacts = _run_api_validation(settings, args)
    warehouse_result = _load_validation_to_warehouse(
        settings,
        api_artifacts.validation_artifacts,
    )
    return {
        **_api_validation_payload(api_artifacts),
        "warehouse": {
            "valid_price_rows_received": warehouse_result.valid_price_rows_received,
            "fact_rows_affected": warehouse_result.fact_rows_affected,
            "quality_issues_logged": warehouse_result.quality_issues_logged,
        },
    }


def _deploy_views(settings: Settings) -> dict[str, Any]:
    settings.require_database_url()
    loader = WarehouseLoader(settings)
    try:
        loader.apply_core_schema()
        loader.apply_dashboard_views()
        return {"dashboard_views": str(loader.dashboard_views_path), "status": "deployed"}
    finally:
        loader.close()


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.command == "show-config":
            result: dict[str, Any] = settings.redacted()
        elif args.command == "deploy-views":
            result = _deploy_views(settings)
        elif args.command == "extract-api":
            result = _extract_api(settings, args)
        elif args.command == "extract-csv":
            result = _extract_csv(settings, args)
        elif args.command == "validate-csv":
            result = _validate_csv(settings, args)
        elif args.command == "load-csv":
            result = _load_csv(settings, args)
        elif args.command == "validate-api":
            result = _validate_api(settings, args)
        elif args.command == "load-api":
            result = _load_api(settings, args)
        else:
            raise AssertionError(f"Unhandled command: {args.command}")
    except (
        ConfigurationError,
        DataGovExtractionError,
        CsvSourceError,
        DataQualityReportError,
        ProcessedDatasetError,
        RawReceiptError,
        WarehouseError,
        ValueError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    print(json.dumps(result, default=str, indent=2, sort_keys=True))
    return 0
