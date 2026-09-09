import json
from pathlib import Path


def test_powerbi_theme_is_valid_and_dashboard_assets_cover_required_kpis() -> None:
    powerbi_directory = Path(__file__).resolve().parents[1] / "powerbi"
    theme = json.loads(
        (powerbi_directory / "farmeasy_mandi_theme.json").read_text(encoding="utf-8")
    )
    dax = (powerbi_directory / "farmeasy_mandi_measures.dax").read_text(encoding="utf-8")
    guide = (Path(__file__).resolve().parents[1] / "docs/powerbi-build-guide.md").read_text(
        encoding="utf-8"
    )

    assert theme["name"] == "FarmEasy Mandi"
    assert len(theme["dataColors"]) >= 6
    for measure_name in (
        "Latest Average Modal Price",
        "7-Day Average Modal Price",
        "30-Day Average Modal Price",
        "Week-over-Week Change %",
        "Month-over-Month Change %",
        "Modal Price Coefficient of Variation %",
        "Data Freshness Days",
        "Missing Reporting Rate %",
    ):
        assert measure_name in dax
    for page_name in (
        "Executive Overview",
        "Commodity Price Explorer",
        "Best Mandi Comparison",
        "Volatility and Risk",
        "Data Quality",
        "Supply and Arrivals — conditional only",
    ):
        assert page_name in guide
    assert "Relationships" in guide
    assert "drill-through" in guide
