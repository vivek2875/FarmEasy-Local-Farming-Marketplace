"""Local CSV fallback and lossless Data.gov.in source-header mapping.

This module deliberately does not parse dates, coerce numeric values, trim
text, infer units, or reject bad price rows.  Those decisions belong to later
validation and transformation stages.  It only gives API JSON records and CSV
columns one stable *source* shape before that work begins.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from .raw_storage import RawReceipt, RawReceiptStore

SOURCE_PRICE_HEADERS = (
    "arrival_date",
    "state",
    "district",
    "market",
    "commodity",
    "variety",
    "grade",
    "min_price",
    "max_price",
    "modal_price",
    "price_unit",
    "arrival_quantity",
    "arrival_unit",
    "source_record_id",
)

_ENCODED_CHARACTER = re.compile(r"_x([0-9a-fA-F]{4})_")
_HEADER_SEPARATOR = re.compile(r"[\s\-./()\[\]{}]+")
_MULTIPLE_UNDERSCORES = re.compile(r"_+")


def _header_key(header: str) -> str:
    """Normalise a header for alias lookup only; record values are untouched."""
    decoded = _ENCODED_CHARACTER.sub(lambda match: chr(int(match.group(1), 16)), header)
    separated = _HEADER_SEPARATOR.sub("_", decoded.lstrip("\ufeff").strip().casefold())
    return _MULTIPLE_UNDERSCORES.sub("_", separated).strip("_")


def _alias_map() -> dict[str, str]:
    aliases = {
        "arrival_date": (
            "arrival_date",
            "arrival date",
            "date",
            "price date",
            "market date",
        ),
        "state": ("state", "state name"),
        "district": ("district", "district name"),
        "market": ("market", "market name", "mandi", "mandi name"),
        "commodity": ("commodity", "commodity name", "crop", "crop name"),
        "variety": ("variety", "variety name"),
        "grade": ("grade", "quality", "quality grade"),
        "min_price": (
            "min_price",
            "min price",
            "minimum price",
            "min price (rs./quintal)",
            "minimum price (rs./quintal)",
        ),
        "max_price": (
            "max_price",
            "max price",
            "maximum price",
            "max price (rs./quintal)",
            "maximum price (rs./quintal)",
        ),
        "modal_price": (
            "modal_price",
            "modal price",
            "modal price (rs./quintal)",
        ),
        "price_unit": ("price_unit", "price unit", "price uom", "price unit of measure"),
        "arrival_quantity": (
            "arrival_quantity",
            "arrival quantity",
            "arrival qty",
            "arrivals",
            "arrivals (tonnes)",
            "arrival quantity (tonnes)",
        ),
        "arrival_unit": (
            "arrival_unit",
            "arrival unit",
            "arrival uom",
            "arrival unit of measure",
        ),
        "source_record_id": ("source_record_id", "record id", "record_id", "_id", "id"),
    }
    return {
        _header_key(alias): canonical for canonical, values in aliases.items() for alias in values
    }


DATA_GOV_HEADER_ALIASES = _alias_map()


class CsvSourceError(ValueError):
    """Raised for CSV decoding or structural errors before quality validation."""


def canonical_source_header(header: str) -> str:
    """Map an official Data.gov.in header alias to a stable source field name.

    Unknown fields retain their original header exactly so that source-specific
    context is not discarded before a later layer decides whether it matters.
    """
    if not isinstance(header, str):
        raise TypeError("CSV and JSON record headers must be strings.")
    return DATA_GOV_HEADER_ALIASES.get(_header_key(header), header)


def map_source_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Map headers in a source record without modifying any values.

    When a malformed source supplies two aliases for one canonical field, the
    first mapped value remains under the canonical header and later fields keep
    their original header.  This preserves all source values for the quality
    layer instead of silently picking or normalising one.
    """
    mapped: dict[str, Any] = {}
    for header, value in record.items():
        canonical = canonical_source_header(header)
        if canonical in mapped and canonical != header:
            mapped[header] = value
        else:
            mapped[canonical] = value
    return mapped


def map_source_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Apply :func:`map_source_record` to official CSV or JSON records."""
    return [map_source_record(record) for record in records]


# Explicit aliases make API-client integration self-documenting.
map_data_gov_record = map_source_record
map_data_gov_records = map_source_records


@dataclass(frozen=True, slots=True)
class CsvReadResult:
    """Parsed local CSV records plus the optional immutable raw receipt."""

    source_path: Path
    source_name: str
    headers: tuple[str, ...]
    records: tuple[dict[str, Any], ...]
    raw_receipt: RawReceipt | None = None


class CsvSource:
    """Read a local CSV as an offline fallback to the Data.gov.in API."""

    def __init__(
        self,
        source_path: Path | str,
        *,
        source_name: str = "local_csv",
        encoding: str = "utf-8-sig",
        delimiter: str = ",",
    ) -> None:
        if not delimiter or len(delimiter) != 1:
            raise CsvSourceError("delimiter must be one character.")
        self.source_path = Path(source_path)
        self.source_name = source_name
        self.encoding = encoding
        self.delimiter = delimiter

    def read(
        self,
        *,
        raw_store: RawReceiptStore | None = None,
        run_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CsvReadResult:
        """Read local CSV values unchanged, optionally storing raw bytes first."""
        try:
            raw_bytes = self.source_path.read_bytes()
        except OSError as error:
            raise CsvSourceError(f"Could not read CSV source {self.source_path}.") from error

        raw_receipt: RawReceipt | None = None
        if raw_store is not None:
            if not run_id:
                raise CsvSourceError("run_id is required when raw_store is supplied.")
            raw_receipt = raw_store.store_bytes(
                raw_bytes,
                run_id=run_id,
                source_name=self.source_name,
                suffix=self.source_path.suffix or ".csv",
                content_type="text/csv",
                metadata={"source_filename": self.source_path.name, **(metadata or {})},
            )

        try:
            text = raw_bytes.decode(self.encoding)
        except UnicodeDecodeError as error:
            raise CsvSourceError(
                f"CSV source {self.source_path} is not decodable as {self.encoding!r}."
            ) from error

        try:
            reader = csv.DictReader(
                StringIO(text, newline=""),
                delimiter=self.delimiter,
                skipinitialspace=False,
            )
            if not reader.fieldnames:
                raise CsvSourceError(
                    f"CSV source {self.source_path} does not contain a header row."
                )
            if any(header is None or header == "" for header in reader.fieldnames):
                raise CsvSourceError(f"CSV source {self.source_path} has an empty header name.")
            records = []
            for row_number, record in enumerate(reader, start=2):
                if None in record:
                    raise CsvSourceError(
                        f"CSV source {self.source_path} has more values than "
                        f"headers on row {row_number}."
                    )
                records.append(map_source_record(record))
        except csv.Error as error:
            raise CsvSourceError(f"Could not parse CSV source {self.source_path}.") from error

        return CsvReadResult(
            source_path=self.source_path,
            source_name=self.source_name,
            headers=tuple(canonical_source_header(header) for header in reader.fieldnames),
            records=tuple(records),
            raw_receipt=raw_receipt,
        )

    # ``extract`` is a readable pipeline-oriented spelling of ``read``.
    extract = read


CSVSource = CsvSource
CsvFallbackSource = CsvSource


def read_csv_source(
    source_path: Path | str,
    *,
    source_name: str = "local_csv",
    encoding: str = "utf-8-sig",
    delimiter: str = ",",
    raw_store: RawReceiptStore | None = None,
    run_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> CsvReadResult:
    """Convenience entry point for a one-off local CSV fallback read."""
    return CsvSource(
        source_path,
        source_name=source_name,
        encoding=encoding,
        delimiter=delimiter,
    ).read(raw_store=raw_store, run_id=run_id, metadata=metadata)
