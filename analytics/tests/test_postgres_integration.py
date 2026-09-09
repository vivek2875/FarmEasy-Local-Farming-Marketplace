"""Optional integration coverage for a dedicated disposable PostgreSQL test database."""

import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

from farmeasy_mandi_analytics.config import load_settings
from farmeasy_mandi_analytics.load.warehouse import WarehouseLoader
from farmeasy_mandi_analytics.validate.price_rules import validate_price_records


@pytest.mark.integration
def test_postgres_loader_prevents_duplicate_fact_rows() -> None:
    database_url = os.getenv("FARMEASY_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("FARMEASY_TEST_DATABASE_URL is not configured.")

    project_root = Path(__file__).resolve().parents[2]
    settings = load_settings(
        environ={"FARMEASY_ANALYTICS_DATABASE_URL": database_url},
        project_root=project_root,
    )
    unique_suffix = uuid4().hex
    run_id = f"postgres-test-{unique_suffix}"
    source_name = f"postgres_integration_{unique_suffix}"
    validation = validate_price_records(
        [
            {
                "arrival_date": "08/09/2026",
                "state": "Karnataka",
                "district": "Mysuru",
                "market": "Mysuru APMC",
                "commodity": "Tomato",
                "min_price": "1000",
                "max_price": "2000",
                "modal_price": "1500",
            }
        ],
        source_name=source_name,
        price_unit="INR/quintal",
        reference_date=date(2026, 9, 8),
    )
    loader = WarehouseLoader(settings)
    try:
        first = loader.load_validation_result(
            validation,
            run_id=run_id,
            source_name=source_name,
        )
        second = loader.load_validation_result(
            validation,
            run_id=run_id,
            source_name=source_name,
            ensure_schema=False,
        )
        with loader.engine.connect() as connection:
            fact_count = connection.execute(
                text(
                    "SELECT COUNT(*) FROM analytics.fact_mandi_prices "
                    "WHERE source_name = :source_name"
                ),
                {"source_name": source_name},
            ).scalar_one()
    finally:
        loader.close()

    assert first.fact_rows_affected == 1
    assert second.fact_rows_affected == 0
    assert fact_count == 1
