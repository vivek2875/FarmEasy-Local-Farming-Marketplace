from hashlib import sha256

from farmeasy_mandi_analytics.extract.csv_source import (
    CsvSource,
    canonical_source_header,
    map_source_record,
)
from farmeasy_mandi_analytics.extract.raw_storage import RawReceiptStore


def test_data_gov_aliases_map_to_source_headers_without_changing_values() -> None:
    source_record = {
        "Arrival_Date": " 08/09/2026 ",
        "State": "  Karnataka  ",
        "Market": " Mysuru ",
        "Min_x0020_Price": "001000.50",
        "Max_x0020_Price": "2000",
        "Modal_x0020_Price": " 1500 ",
        "Custom Note": "do not trim me ",
    }

    mapped = map_source_record(source_record)

    assert mapped == {
        "arrival_date": " 08/09/2026 ",
        "state": "  Karnataka  ",
        "market": " Mysuru ",
        "min_price": "001000.50",
        "max_price": "2000",
        "modal_price": " 1500 ",
        "Custom Note": "do not trim me ",
    }


def test_human_readable_data_gov_price_aliases_are_supported() -> None:
    assert canonical_source_header("Min Price (Rs./Quintal)") == "min_price"
    assert canonical_source_header("Maximum Price (Rs./Quintal)") == "max_price"
    assert canonical_source_header("Modal Price (Rs./Quintal)") == "modal_price"
    assert canonical_source_header("Arrival_x0020_Quantity") == "arrival_quantity"


def test_csv_fallback_maps_headers_and_stores_the_original_bytes(tmp_path) -> None:
    source_path = tmp_path / "official-export.csv"
    raw_bytes = (
        b"\xef\xbb\xbfArrival_Date,State,District,Market,Commodity,Min_x0020_Price,"
        b"Max_x0020_Price,Modal_x0020_Price\r\n"
        b"08/09/2026, Karnataka ,Mysuru, Mysuru AP ,Tomato,1000,2200, 1500 \r\n"
    )
    source_path.write_bytes(raw_bytes)
    store = RawReceiptStore(tmp_path / "raw")

    result = CsvSource(source_path, source_name="local_official_csv").read(
        raw_store=store,
        run_id="csv-run-1",
    )

    assert result.headers[:5] == ("arrival_date", "state", "district", "market", "commodity")
    assert result.records == (
        {
            "arrival_date": "08/09/2026",
            "state": " Karnataka ",
            "district": "Mysuru",
            "market": " Mysuru AP ",
            "commodity": "Tomato",
            "min_price": "1000",
            "max_price": "2200",
            "modal_price": " 1500 ",
        },
    )
    assert result.raw_receipt is not None
    assert result.raw_receipt.receipt_path.read_bytes() == raw_bytes
    assert result.raw_receipt.sha256 == sha256(raw_bytes).hexdigest()
