"""Safe, paginated extraction from Data.gov.in resource APIs.

The Data.gov.in resource endpoint uses query parameters rather than a bespoke
SDK: ``api-key``, ``format``, ``offset``, and ``limit``.  This module keeps the
response bytes alongside decoded records so the raw-receipt layer can preserve
an exact, auditable source response before any transformation occurs.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

import httpx

from farmeasy_mandi_analytics.config import Settings

_RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
_MAX_RETRY_DELAY_SECONDS = 60.0
_Clock = Callable[[], datetime]
_Sleep = Callable[[float], None]


class DataGovExtractionError(RuntimeError):
    """Base exception for a Data.gov.in extraction failure.

    Messages intentionally never include URLs, response bodies, or query
    parameters because the API key is supplied in the query string.
    """


class DataGovRequestError(DataGovExtractionError):
    """Raised when a request cannot be completed safely."""


class DataGovPayloadError(DataGovExtractionError):
    """Raised when a successful HTTP response is not a valid resource payload."""


class DataGovPaginationError(DataGovExtractionError):
    """Raised when pagination metadata would make extraction incomplete or loop."""


@dataclass(frozen=True, slots=True)
class DataGovPage:
    """One decoded page and its untouched source response.

    ``response_bytes`` is deliberately retained unchanged.  A later raw-store
    component can fingerprint and persist it without serializing the decoded
    records again. ``total`` is the source-reported matching-record count when
    the response exposes one.
    """

    offset: int
    limit: int
    records: tuple[dict[str, Any], ...]
    total: int | None
    received_at: datetime
    response_bytes: bytes
    content_type: str | None
    status_code: int

    @property
    def raw_bytes(self) -> bytes:
        """Compatibility-friendly name for the immutable raw source receipt."""
        return self.response_bytes

    @property
    def record_count(self) -> int:
        """Return the number of decoded source records in this page."""
        return len(self.records)


class DataGovClient:
    """Synchronous client for the official Data.gov.in resource endpoint.

    The client is deliberately transport-injectable so tests can use
    :class:`httpx.MockTransport` without ever calling a live government API.
    Pass an externally owned ``httpx.Client`` when connection management should
    remain with the caller; otherwise this instance manages its own client.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: httpx.Client | None = None,
        sleep: _Sleep | None = None,
        clock: _Clock | None = None,
    ) -> None:
        api_key, resource_id = settings.require_data_gov_credentials()
        self._api_key = api_key
        self._resource_url = f"{settings.data_gov_api_url}/{quote(resource_id, safe='')}"
        self._page_size = settings.page_size
        self._timeout_seconds = settings.request_timeout_seconds
        self._max_retries = settings.max_retries
        self._retry_backoff_seconds = settings.retry_backoff_seconds
        self._client = client or httpx.Client(
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(self._timeout_seconds),
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._sleep = sleep or time.sleep
        self._clock = clock or _utc_now

    def __enter__(self) -> DataGovClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """Close only the HTTP client created by this extractor."""
        if self._owns_client:
            self._client.close()
            self._owns_client = False

    def fetch_page(
        self,
        offset: int,
        *,
        filters: Mapping[str, str | int | float] | None = None,
    ) -> DataGovPage:
        """Fetch one official resource page at a zero-based ``offset``.

        ``filters`` uses source field names, such as ``{"state": "Bihar"}``.
        They are encoded using Data.gov.in's ``filters[field]`` query format;
        callers cannot override pagination or authentication parameters.
        """
        _validate_offset(offset)
        response = self._request_page(offset, self._build_params(offset, filters))
        response_bytes = response.content
        payload = _decode_payload(response_bytes, offset)
        records = _extract_records(payload, offset)
        total = _extract_total(payload, offset)

        return DataGovPage(
            offset=offset,
            limit=self._page_size,
            records=records,
            total=total,
            received_at=self._clock(),
            response_bytes=response_bytes,
            content_type=response.headers.get("content-type"),
            status_code=response.status_code,
        )

    def iter_pages(
        self,
        *,
        filters: Mapping[str, str | int | float] | None = None,
    ) -> Iterator[DataGovPage]:
        """Yield every page until the source-reported total is exhausted.

        When a resource does not provide ``total``, a short page signals the
        end. A nonempty result is required while a reported total says records
        remain; failing clearly is safer than quietly creating an incomplete
        warehouse load.
        """
        normalized_filters = _normalize_filters(filters)
        offset = 0

        while True:
            page = self.fetch_page(offset, filters=normalized_filters)
            if page.total is not None and page.record_count == 0 and page.total > offset:
                raise DataGovPaginationError(
                    "Data.gov.in returned an empty page while its total indicates "
                    f"more records at offset {offset}."
                )

            yield page

            if page.total is not None:
                if offset + page.record_count >= page.total:
                    return
            elif page.record_count < self._page_size:
                return

            if page.record_count == 0:
                # A source without a total returned an empty page. This is an
                # unambiguous terminal response and prevents a retry-free loop.
                return

            offset += page.record_count

    def _build_params(
        self,
        offset: int,
        filters: Mapping[str, str | int | float] | None,
    ) -> dict[str, str]:
        params = _normalize_filters(filters)
        params.update(
            {
                "api-key": self._api_key,
                "format": "json",
                "offset": str(offset),
                "limit": str(self._page_size),
            }
        )
        return params

    def _request_page(self, offset: int, params: Mapping[str, str]) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(
                    self._resource_url,
                    params=params,
                    timeout=self._timeout_seconds,
                )
            except httpx.RequestError:
                if attempt == self._max_retries:
                    raise DataGovRequestError(
                        "Data.gov.in request failed after "
                        f"{attempt + 1} attempt(s) for offset {offset}."
                    ) from None
                self._sleep(self._retry_delay(attempt, None))
                continue

            if response.status_code in _RETRYABLE_STATUS_CODES:
                if attempt == self._max_retries:
                    raise DataGovRequestError(
                        "Data.gov.in returned retryable HTTP "
                        f"{response.status_code} after {attempt + 1} attempt(s) "
                        f"for offset {offset}."
                    )
                self._sleep(self._retry_delay(attempt, response))
                continue

            if response.is_error:
                raise DataGovRequestError(
                    f"Data.gov.in returned HTTP {response.status_code} for offset {offset}."
                )

            return response

        # The loop always returns or raises. This guard satisfies type checkers
        # and keeps a future control-flow change from silently returning None.
        raise AssertionError("Unreachable Data.gov.in request state")

    def _retry_delay(self, attempt: int, response: httpx.Response | None) -> float:
        retry_after = _retry_after_seconds(response)
        if retry_after is not None:
            return retry_after
        # Cap exponentiation and delay to prevent an accidentally huge setting
        # from turning a transient source failure into an unbounded wait.
        return min(
            self._retry_backoff_seconds * (2 ** min(attempt, 16)),
            _MAX_RETRY_DELAY_SECONDS,
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _validate_offset(offset: int) -> None:
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer.")


def _normalize_filters(
    filters: Mapping[str, str | int | float] | None,
) -> dict[str, str]:
    if filters is None:
        return {}

    normalized: dict[str, str] = {}
    for field_name, value in filters.items():
        field = str(field_name).strip()
        if not field or "[" in field or "]" in field:
            raise ValueError("Data.gov.in filter names must be nonempty field names.")
        if value is None or isinstance(value, bool):
            raise ValueError("Data.gov.in filter values must be text or numbers.")
        normalized[f"filters[{field}]"] = str(value)
    return normalized


def _decode_payload(response_bytes: bytes, offset: int) -> Mapping[str, Any]:
    try:
        payload = json.loads(response_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DataGovPayloadError(
            f"Data.gov.in returned invalid JSON for offset {offset}."
        ) from error
    if not isinstance(payload, dict):
        raise DataGovPayloadError(
            f"Data.gov.in returned a JSON payload that is not an object for offset {offset}."
        )
    return payload


def _extract_records(payload: Mapping[str, Any], offset: int) -> tuple[dict[str, Any], ...]:
    records = payload.get("records")
    if not isinstance(records, list):
        raise DataGovPayloadError(
            f"Data.gov.in response is missing a records list for offset {offset}."
        )

    decoded_records: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            raise DataGovPayloadError(
                f"Data.gov.in records must be JSON objects for offset {offset}."
            )
        decoded_records.append(dict(record))
    return tuple(decoded_records)


def _extract_total(payload: Mapping[str, Any], offset: int) -> int | None:
    if "total" not in payload or payload["total"] is None:
        return None

    raw_total = payload["total"]
    if isinstance(raw_total, bool):
        raise DataGovPayloadError(f"Data.gov.in total is invalid for offset {offset}.")
    try:
        total = int(raw_total)
    except (TypeError, ValueError) as error:
        raise DataGovPayloadError(f"Data.gov.in total is invalid for offset {offset}.") from error
    if total < 0 or (isinstance(raw_total, float) and not raw_total.is_integer()):
        raise DataGovPayloadError(f"Data.gov.in total is invalid for offset {offset}.")
    return total


def _retry_after_seconds(response: httpx.Response | None) -> float | None:
    if response is None:
        return None
    raw_value = response.headers.get("retry-after")
    if raw_value is None:
        return None
    try:
        seconds = float(raw_value)
    except ValueError:
        return None
    if seconds < 0:
        return None
    return min(seconds, _MAX_RETRY_DELAY_SECONDS)
