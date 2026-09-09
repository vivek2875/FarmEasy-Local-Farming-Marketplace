"""Atomic storage for derived, non-raw local datasets."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

VALIDATED_MANDI_PRICES_FILENAME = "validated_mandi_prices.csv"
_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ProcessedDatasetError(ValueError):
    """Raised when a derived dataset cannot be written safely."""


@dataclass(frozen=True, slots=True)
class ProcessedDatasetArtifacts:
    """Location and row count for one derived mandi-price dataset."""

    run_id: str
    valid_price_rows: int
    validated_prices_path: Path


def _require_safe_run_id(run_id: str) -> str:
    if not _SAFE_RUN_ID.fullmatch(run_id):
        raise ProcessedDatasetError(
            "run_id must contain only letters, numbers, dots, underscores, or hyphens "
            "and must not contain path separators."
        )
    return run_id


class ProcessedDatasetWriter:
    """Persist the validated dataset atomically, replacing only the same run's output."""

    def __init__(self, processed_dir: Path | str) -> None:
        self.processed_dir = Path(processed_dir)

    def write_validated_prices(
        self,
        valid_rows: pd.DataFrame,
        *,
        run_id: str,
    ) -> ProcessedDatasetArtifacts:
        """Write an analysis-ready CSV after validation and transformation."""
        safe_run_id = _require_safe_run_id(run_id)
        destination = self.processed_dir / safe_run_id / VALIDATED_MANDI_PRICES_FILENAME
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=destination.parent,
                prefix=f".{destination.stem}-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                valid_rows.to_csv(temporary_file, index=False, lineterminator="\n")
                temporary_name = temporary_file.name
            os.replace(temporary_name, destination)
        except (OSError, ValueError) as error:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
            raise ProcessedDatasetError(
                f"Could not write processed dataset {destination}."
            ) from error
        return ProcessedDatasetArtifacts(
            run_id=safe_run_id,
            valid_price_rows=len(valid_rows),
            validated_prices_path=destination,
        )
