from decimal import Decimal

import pandas as pd
import pytest

from farmeasy_mandi_analytics.storage.processed import (
    ProcessedDatasetError,
    ProcessedDatasetWriter,
)


def test_processed_writer_replaces_only_the_same_run_output_atomically(tmp_path) -> None:
    writer = ProcessedDatasetWriter(tmp_path / "processed")
    first = writer.write_validated_prices(
        pd.DataFrame({"market_date": ["2026-09-08"], "modal_price": [Decimal("1500")]}),
        run_id="processed-run-1",
    )
    second = writer.write_validated_prices(
        pd.DataFrame({"market_date": ["2026-09-08"], "modal_price": [Decimal("1600")]}),
        run_id="processed-run-1",
    )

    assert first.validated_prices_path == second.validated_prices_path
    assert second.valid_price_rows == 1
    assert "1600" in second.validated_prices_path.read_text(encoding="utf-8")
    assert "1500" not in second.validated_prices_path.read_text(encoding="utf-8")


def test_processed_writer_rejects_an_unsafe_run_id(tmp_path) -> None:
    with pytest.raises(ProcessedDatasetError, match="path separators"):
        ProcessedDatasetWriter(tmp_path).write_validated_prices(
            pd.DataFrame(),
            run_id="../unsafe",
        )
