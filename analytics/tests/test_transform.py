from datetime import date
from pathlib import Path

from farmeasy_mandi_analytics.config import load_settings
from farmeasy_mandi_analytics.transform.mandi_prices import transform_price_records


def test_transform_maps_official_csv_headers_before_validation() -> None:
    project_root = Path(__file__).resolve().parents[2]
    settings = load_settings(environ={}, project_root=project_root)
    records = [
        {
            "Arrival_Date": "08/09/2026",
            "State": "orissa",
            "District": "khordha",
            "Market": "bhubaneswar apmc",
            "Commodity": "tomato",
            "Min_x0020_Price": "1000",
            "Max_x0020_Price": "2000",
            "Modal_x0020_Price": "1500",
        }
    ]

    result = transform_price_records(
        records,
        settings=settings,
        source_name="local_official_csv",
        reference_date=date(2026, 9, 8),
    )

    row = result.valid_rows.iloc[0]
    assert row["state"] == "Odisha"
    assert row["market"] == "Bhubaneswar APMC"
