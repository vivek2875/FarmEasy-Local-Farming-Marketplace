import json
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from farmeasy_mandi_analytics.extract.raw_storage import RawReceiptError, RawReceiptStore


def test_raw_receipt_preserves_exact_bytes_and_records_a_sha256_manifest(tmp_path) -> None:
    payload = b"\xef\xbb\xbfArrival_Date,Min_x0020_Price\r\n2026-09-01,1234\r\n"
    captured_at = datetime(2026, 9, 8, 3, 15, tzinfo=UTC)
    store = RawReceiptStore(tmp_path / "raw")

    receipt = store.store_bytes(
        payload,
        run_id="run-20260908",
        source_name="data_gov_in",
        suffix="csv",
        content_type="text/csv",
        metadata={"page_offset": 0},
        captured_at=captured_at,
    )

    assert receipt.receipt_path.read_bytes() == payload
    assert receipt.sha256 == sha256(payload).hexdigest()
    assert receipt.captured_at == "2026-09-08T03:15:00Z"

    manifest = json.loads(receipt.manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run-20260908"
    assert manifest["receipts"] == [
        {
            "byte_count": len(payload),
            "captured_at": "2026-09-08T03:15:00Z",
            "content_type": "text/csv",
            "metadata": {"page_offset": 0},
            "raw_file": f"receipts/data_gov_in-{sha256(payload).hexdigest()}.csv",
            "sha256": sha256(payload).hexdigest(),
            "source_name": "data_gov_in",
        }
    ]


def test_repeat_raw_receipt_is_idempotent_per_run(tmp_path) -> None:
    store = RawReceiptStore(tmp_path / "raw")
    first = store.store_bytes(b'{"records":[]}', run_id="run-1", source_name="data_gov_in")
    second = store.store_bytes(b'{"records":[]}', run_id="run-1", source_name="data_gov_in")

    manifest = store.read_manifest("run-1")
    assert first.receipt_path == second.receipt_path
    assert first.sha256 == second.sha256
    assert len(manifest["receipts"]) == 1


def test_manifest_redacts_nested_credentials_and_url_query_values(tmp_path) -> None:
    store = RawReceiptStore(tmp_path / "raw")
    receipt = store.store_bytes(
        b"safe payload",
        run_id="run-2",
        source_name="data_gov_in",
        metadata={
            "url": "https://api.data.gov.in/resource?api-key=should-not-appear&limit=100",
            "headers": {"Authorization": "Bearer should-not-appear"},
            "api_key": "should-not-appear",
            "request": "token=should-not-appear",
        },
    )

    manifest_text = receipt.manifest_path.read_text(encoding="utf-8")
    assert "should-not-appear" not in manifest_text
    manifest = json.loads(manifest_text)
    metadata = manifest["receipts"][0]["metadata"]
    assert metadata["api_key"] == "***redacted***"
    assert metadata["headers"]["Authorization"] == "***redacted***"
    assert "api-key=%2A%2A%2Aredacted%2A%2A%2A" in metadata["url"]
    assert metadata["request"] == "token=***redacted***"


@pytest.mark.parametrize("run_id", ["../escape", "run/name", "", "run name"])
def test_unsafe_run_identifiers_are_rejected(tmp_path, run_id: str) -> None:
    store = RawReceiptStore(tmp_path / "raw")

    with pytest.raises(RawReceiptError):
        store.store_bytes(b"payload", run_id=run_id, source_name="local_csv")
