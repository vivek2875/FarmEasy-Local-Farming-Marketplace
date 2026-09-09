import json
from contextlib import AbstractContextManager
from datetime import date
from pathlib import Path
from typing import Any

from farmeasy_mandi_analytics.config import load_settings
from farmeasy_mandi_analytics.load.warehouse import (
    WarehouseLoader,
    _date_dimensions,
    _date_range,
    _redact_configuration_snapshot,
)
from farmeasy_mandi_analytics.validate.price_rules import validate_price_records


class _FakeResult:
    def __init__(self, *, rowcount: int = 1, scalar: int | None = None) -> None:
        self.rowcount = rowcount
        self._scalar = scalar

    def scalar_one(self) -> int:
        assert self._scalar is not None
        return self._scalar


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.schema_scripts: list[str] = []
        self._next_key = 1
        self._facts: dict[tuple[str, str], tuple[Any, ...]] = {}
        self._issues: set[tuple[str, str]] = set()

    def exec_driver_sql(self, statement: str) -> None:
        self.schema_scripts.append(statement)

    def execute(self, statement, parameters=None) -> _FakeResult:
        sql = statement.text
        params = dict(parameters or {})
        self.calls.append((sql, params))
        if "RETURNING location_key" in sql or "RETURNING market_key" in sql:
            key = self._next_key
            self._next_key += 1
            return _FakeResult(scalar=key)
        if "RETURNING commodity_key" in sql:
            key = self._next_key
            self._next_key += 1
            return _FakeResult(scalar=key)
        if "INSERT INTO analytics.fact_mandi_prices" in sql:
            identity = (params["source_name"], params["source_observation_hash"])
            content = (
                params["source_content_hash"],
                params["source_record_id"],
                params["quality_status"],
                params["quality_warning_codes"],
            )
            unchanged = self._facts.get(identity) == content
            self._facts[identity] = content
            return _FakeResult(rowcount=0 if unchanged else 1)
        if "INSERT INTO analytics.data_quality_log" in sql:
            identity = (params["run_id"], params["issue_hash"])
            if identity in self._issues:
                return _FakeResult(rowcount=0)
            self._issues.add(identity)
            return _FakeResult(rowcount=1)
        return _FakeResult()


class _FakeTransaction(AbstractContextManager):
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _FakeConnection:
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class _FakeEngine:
    def __init__(self) -> None:
        self.connection = _FakeConnection()
        self.disposed = False

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self.connection)

    def dispose(self) -> None:
        self.disposed = True


def _record(**overrides: str) -> dict[str, str]:
    record = {
        "arrival_date": "01/09/2026",
        "state": "Karnataka",
        "district": "Mysuru",
        "market": "Mysuru APMC",
        "commodity": "Tomato",
        "min_price": "900",
        "max_price": "2200",
        "modal_price": "1000",
    }
    record.update(overrides)
    return record


def test_warehouse_loader_uses_parameterized_idempotent_upserts(tmp_path) -> None:
    project_root = Path(__file__).resolve().parents[2]
    settings = load_settings(environ={}, project_root=project_root)
    engine = _FakeEngine()
    loader = WarehouseLoader(settings, engine=engine)  # type: ignore[arg-type]
    validation = validate_price_records(
        [
            _record(),
            _record(arrival_date="02/09/2026", modal_price="2000"),
        ],
        source_name="data_gov_current_mandi",
        price_unit="INR/quintal",
        suspicious_change_pct=50,
        reference_date=date(2026, 9, 2),
    )

    first = loader.load_validation_result(
        validation,
        run_id="warehouse-run-1",
        source_name="data_gov_current_mandi",
        raw_manifest_path=tmp_path / "manifest.json",
        configuration_snapshot={
            "database_url": "postgresql://user:real-password@example.test/farmeasy",
            "page_size": 1000,
        },
    )
    second = loader.load_validation_result(
        validation,
        run_id="warehouse-run-1",
        source_name="data_gov_current_mandi",
        ensure_schema=False,
    )

    fact_sql = next(sql for sql, _ in engine.connection.calls if "fact_mandi_prices" in sql)
    assert first.fact_rows_affected == 2
    assert first.quality_issues_logged == 1
    assert second.fact_rows_affected == 0
    assert second.quality_issues_logged == 0
    assert "ON CONFLICT (source_name, source_observation_hash)" in fact_sql
    assert "WHERE analytics.fact_mandi_prices.source_content_hash" in fact_sql
    assert "data_gov_current_mandi" not in fact_sql
    assert engine.connection.schema_scripts
    start_params = next(
        params
        for sql, params in engine.connection.calls
        if "INSERT INTO analytics.pipeline_run_log" in sql
    )
    assert "real-password" not in start_params["configuration_snapshot"]
    assert json.loads(start_params["configuration_snapshot"])["database_url"] == "***redacted***"


def test_date_dimension_and_snapshot_redaction_are_deterministic() -> None:
    assert _date_range(date(2026, 9, 1), date(2026, 9, 3)) == [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]
    assert _date_dimensions(date(2026, 9, 8)) == {
        "date_key": 20260908,
        "full_date": date(2026, 9, 8),
        "calendar_year": 2026,
        "calendar_quarter": 3,
        "calendar_month": 9,
        "month_name": "September",
        "iso_week": 37,
        "day_of_month": 8,
        "day_of_week": 2,
        "day_name": "Tuesday",
        "is_weekend": False,
    }
    assert _redact_configuration_snapshot(
        {
            "FARMEASY_ANALYTICS_DATA_GOV_API_KEY": "real-key",
            "nested": {"password": "real-password"},
            "database_url": "postgresql://user:real-password@example.test/db",
        }
    ) == {
        "FARMEASY_ANALYTICS_DATA_GOV_API_KEY": "***redacted***",
        "nested": {"password": "***redacted***"},
        "database_url": "***redacted***",
    }


def test_dashboard_view_deployment_uses_the_versioned_view_definition() -> None:
    project_root = Path(__file__).resolve().parents[2]
    settings = load_settings(environ={}, project_root=project_root)
    engine = _FakeEngine()
    loader = WarehouseLoader(settings, engine=engine)  # type: ignore[arg-type]

    loader.apply_dashboard_views()

    assert loader.dashboard_views_path.name == "001_dashboard_views.sql"
    assert (
        "CREATE OR REPLACE VIEW analytics.vw_dashboard_price_trends"
        in (engine.connection.schema_scripts[0])
    )
