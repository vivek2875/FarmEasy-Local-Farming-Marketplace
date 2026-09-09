from pathlib import Path


def test_dashboard_views_cover_trends_comparison_volatility_freshness_and_quality() -> None:
    views_path = Path(__file__).resolve().parents[1] / "sql/views/001_dashboard_views.sql"
    views = views_path.read_text(encoding="utf-8")

    for view_name in (
        "vw_mandi_price_observations",
        "vw_dashboard_price_trends",
        "vw_dashboard_latest_market_comparison",
        "vw_dashboard_volatility",
        "vw_dashboard_market_freshness",
        "vw_dashboard_reporting_coverage",
        "vw_dashboard_data_quality",
    ):
        assert f"analytics.{view_name}" in views
    assert "RANGE BETWEEN INTERVAL '6 days' PRECEDING" in views
    assert "RANGE BETWEEN INTERVAL '29 days' PRECEDING" in views
    assert "DENSE_RANK() OVER" in views
    assert "STDDEV_SAMP(modal_price)" in views
    assert "COUNT(*) FILTER" in views
