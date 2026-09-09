from pathlib import Path


def test_core_schema_contains_the_required_star_schema_and_idempotency_constraint() -> None:
    schema_path = Path(__file__).resolve().parents[1] / "sql/schema/001_analytics_schema.sql"
    schema = schema_path.read_text(encoding="utf-8")

    for table_name in (
        "pipeline_run_log",
        "dim_date",
        "dim_location",
        "dim_market",
        "dim_commodity",
        "fact_mandi_prices",
        "data_quality_log",
    ):
        assert f"analytics.{table_name}" in schema
    assert "uq_fact_mandi_prices_source_observation" in schema
    assert "idx_fact_mandi_prices_commodity_date" in schema
    assert "idx_data_quality_log_run" in schema


def test_arrival_schema_is_explicitly_optional_until_a_source_is_verified() -> None:
    arrivals_path = (
        Path(__file__).resolve().parents[1] / "sql/schema/002_optional_arrivals_schema.sql"
    )
    schema = arrivals_path.read_text(encoding="utf-8")

    assert "OPTIONAL" in schema
    assert "does not meet that condition" in schema
    assert "analytics.fact_market_arrivals" in schema
