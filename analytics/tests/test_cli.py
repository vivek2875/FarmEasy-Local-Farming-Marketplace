import json
from datetime import UTC, datetime

from farmeasy_mandi_analytics.cli import main
from farmeasy_mandi_analytics.extract.data_gov import DataGovPage
from farmeasy_mandi_analytics.load.warehouse import WarehouseLoadResult


def test_show_config_emits_a_redacted_json_summary(capsys) -> None:
    exit_code = main(["show-config"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["data_gov_api_key"] is None
    assert captured.err == ""


def test_extract_api_fails_before_request_when_api_key_is_missing(monkeypatch, capsys) -> None:
    monkeypatch.delenv("FARMEASY_ANALYTICS_DATA_GOV_API_KEY", raising=False)

    exit_code = main(["extract-api"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "DATA_GOV_API_KEY" in captured.err


def test_extract_csv_persists_a_local_receipt_and_returns_a_summary(
    tmp_path, monkeypatch, capsys
) -> None:
    source_path = tmp_path / "official.csv"
    source_path.write_text(
        "State,District,Market,Commodity,Arrival_Date,Min_x0020_Price,"
        "Max_x0020_Price,Modal_x0020_Price\n"
        "Karnataka,Mysuru,Mysuru AP,Tomato,08/09/2026,1000,2200,1500\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FARMEASY_ANALYTICS_RAW_DIR", str(tmp_path / "raw"))

    exit_code = main(
        [
            "extract-csv",
            str(source_path),
            "--run-id",
            "cli-csv-run",
            "--official-source-url",
            "https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["records_received"] == 1
    assert (tmp_path / "raw" / "cli-csv-run" / "manifest.json").exists()


def test_extract_api_rejects_an_invalid_partial_page_limit(capsys) -> None:
    exit_code = main(["extract-api", "--max-pages", "0"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--max-pages" in captured.err


def test_validate_csv_writes_processed_rows_and_quality_evidence(
    tmp_path, monkeypatch, capsys
) -> None:
    source_path = tmp_path / "official.csv"
    source_path.write_text(
        "State,District,Market,Commodity,Arrival_Date,Min_x0020_Price,"
        "Max_x0020_Price,Modal_x0020_Price\n"
        "Karnataka,Mysuru,Mysuru APMC,Tomato,08/09/2026,1000,2200,1500\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FARMEASY_ANALYTICS_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("FARMEASY_ANALYTICS_PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("FARMEASY_ANALYTICS_QUALITY_REPORTS_DIR", str(tmp_path / "quality"))

    exit_code = main(
        [
            "validate-csv",
            str(source_path),
            "--run-id",
            "cli-validation-run",
            "--reference-date",
            "2026-09-08",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["valid_rows"] == 1
    assert payload["invalid_rows"] == 0
    assert (tmp_path / "processed" / "cli-validation-run" / "validated_mandi_prices.csv").exists()
    assert (tmp_path / "quality" / "cli-validation-run" / "data_quality_report.json").exists()


def test_validate_csv_rejects_an_invalid_reference_date(tmp_path, capsys) -> None:
    source_path = tmp_path / "official.csv"
    source_path.write_text("State\nKarnataka\n", encoding="utf-8")

    exit_code = main(["validate-csv", str(source_path), "--reference-date", "08/09/2026"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "reference-date" in captured.err


def test_load_csv_runs_the_full_pipeline_with_a_configured_warehouse(
    tmp_path, monkeypatch, capsys
) -> None:
    class FakeWarehouseLoader:
        def __init__(self, settings) -> None:
            self.settings = settings
            self.closed = False

        def load_validation_result(self, result, **kwargs) -> WarehouseLoadResult:
            assert kwargs["run_id"] == "cli-load-run"
            assert kwargs["source_name"] == "local_official_csv"
            assert len(result.valid_rows) == 1
            return WarehouseLoadResult(
                run_id="cli-load-run",
                source_name="local_official_csv",
                valid_price_rows_received=1,
                fact_rows_affected=1,
                quality_issues_logged=0,
            )

        def close(self) -> None:
            self.closed = True

    source_path = tmp_path / "official.csv"
    source_path.write_text(
        "State,District,Market,Commodity,Arrival_Date,Min_x0020_Price,"
        "Max_x0020_Price,Modal_x0020_Price\n"
        "Karnataka,Mysuru,Mysuru APMC,Tomato,08/09/2026,1000,2200,1500\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "FARMEASY_ANALYTICS_DATABASE_URL",
        "postgresql+psycopg://test:test@localhost/farmeasy_test",
    )
    monkeypatch.setenv("FARMEASY_ANALYTICS_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("FARMEASY_ANALYTICS_PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("FARMEASY_ANALYTICS_QUALITY_REPORTS_DIR", str(tmp_path / "quality"))
    monkeypatch.setattr("farmeasy_mandi_analytics.cli.WarehouseLoader", FakeWarehouseLoader)

    exit_code = main(
        [
            "load-csv",
            str(source_path),
            "--run-id",
            "cli-load-run",
            "--reference-date",
            "2026-09-08",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["warehouse"] == {
        "fact_rows_affected": 1,
        "quality_issues_logged": 0,
        "valid_price_rows_received": 1,
    }


def test_load_csv_fails_before_reading_source_when_database_url_is_missing(
    tmp_path, monkeypatch, capsys
) -> None:
    source_path = tmp_path / "official.csv"
    source_path.write_text("State\nKarnataka\n", encoding="utf-8")
    raw_directory = tmp_path / "raw"
    monkeypatch.delenv("FARMEASY_ANALYTICS_DATABASE_URL", raising=False)
    monkeypatch.setenv("FARMEASY_ANALYTICS_RAW_DIR", str(raw_directory))

    exit_code = main(["load-csv", str(source_path), "--run-id", "missing-database-run"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "DATABASE_URL" in captured.err
    assert not raw_directory.exists()


def test_validate_api_preserves_mocked_pages_before_transforming_them(
    tmp_path, monkeypatch, capsys
) -> None:
    observed_filters: list[dict[str, str] | None] = []

    class FakeDataGovClient:
        def __init__(self, settings) -> None:
            assert settings.data_gov_api_key == "test-api-key"

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def iter_pages(self, *, filters=None):
            observed_filters.append(filters)
            received_at = datetime(2026, 9, 8, tzinfo=UTC)
            yield DataGovPage(
                offset=0,
                limit=1,
                records=(
                    {
                        "arrival_date": "08/09/2026",
                        "state": "Karnataka",
                        "district": "Mysuru",
                        "market": "Mysuru APMC",
                        "commodity": "Tomato",
                        "min_price": "1000",
                        "max_price": "2000",
                        "modal_price": "1500",
                    },
                ),
                total=2,
                received_at=received_at,
                response_bytes=b'{"page": 0}',
                content_type="application/json",
                status_code=200,
            )
            yield DataGovPage(
                offset=1,
                limit=1,
                records=(
                    {
                        "arrival_date": "08/09/2026",
                        "state": "Karnataka",
                        "district": "Mysuru",
                        "market": "Nanjangud APMC",
                        "commodity": "Tomato",
                        "min_price": "1100",
                        "max_price": "2100",
                        "modal_price": "1600",
                    },
                ),
                total=2,
                received_at=received_at,
                response_bytes=b'{"page": 1}',
                content_type="application/json",
                status_code=200,
            )

    monkeypatch.setenv("FARMEASY_ANALYTICS_DATA_GOV_API_KEY", "test-api-key")
    monkeypatch.setenv("FARMEASY_ANALYTICS_RAW_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("FARMEASY_ANALYTICS_PROCESSED_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("FARMEASY_ANALYTICS_QUALITY_REPORTS_DIR", str(tmp_path / "quality"))
    monkeypatch.setattr("farmeasy_mandi_analytics.cli.DataGovClient", FakeDataGovClient)

    exit_code = main(
        [
            "validate-api",
            "--run-id",
            "cli-api-run",
            "--state",
            "Karnataka",
            "--reference-date",
            "2026-09-08",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    manifest = json.loads(
        (tmp_path / "raw" / "cli-api-run" / "manifest.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert observed_filters == [{"state": "Karnataka"}]
    assert payload["pages_preserved"] == 2
    assert payload["records_received"] == 2
    assert payload["valid_rows"] == 2
    assert payload["filters"] == {"state": "Karnataka"}
    assert len(manifest["receipts"]) == 2
