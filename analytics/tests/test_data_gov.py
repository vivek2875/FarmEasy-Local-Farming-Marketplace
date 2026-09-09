from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from farmeasy_mandi_analytics.config import ConfigurationError, load_settings
from farmeasy_mandi_analytics.extract.data_gov import (
    DataGovClient,
    DataGovPaginationError,
    DataGovPayloadError,
    DataGovRequestError,
)


def _settings(**overrides: str) -> object:
    environment = {
        "FARMEASY_ANALYTICS_DATA_GOV_API_KEY": "test-api-key",
        "FARMEASY_ANALYTICS_DATA_GOV_RESOURCE_ID": "test-resource-id",
        "FARMEASY_ANALYTICS_PAGE_SIZE": "2",
        "FARMEASY_ANALYTICS_MAX_RETRIES": "2",
        "FARMEASY_ANALYTICS_RETRY_BACKOFF_SECONDS": "0.25",
    }
    environment.update(overrides)
    return load_settings(environ=environment)


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_page_uses_official_pagination_parameters_and_preserves_raw_bytes() -> None:
    raw_response = b'{"records":[{"commodity":"Onion"}],"total":"1"}'
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return httpx.Response(
            200,
            content=raw_response,
            headers={"content-type": "application/json; charset=utf-8"},
        )

    received_at = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client, clock=lambda: received_at)
        page = client.fetch_page(0, filters={"state": "Bihar"})

    assert page.records == ({"commodity": "Onion"},)
    assert page.total == 1
    assert page.response_bytes == raw_response
    assert page.raw_bytes == raw_response
    assert page.received_at == received_at
    assert page.content_type == "application/json; charset=utf-8"

    assert len(observed_requests) == 1
    request = observed_requests[0]
    assert request.url.path == "/resource/test-resource-id"
    assert dict(request.url.params) == {
        "api-key": "test-api-key",
        "format": "json",
        "offset": "0",
        "limit": "2",
        "filters[state]": "Bihar",
    }


def test_iter_pages_follows_total_and_advances_offsets() -> None:
    observed_offsets: list[str] = []
    responses = [
        {"records": [{"id": "one"}, {"id": "two"}], "total": "3"},
        {"records": [{"id": "three"}], "total": "3"},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        observed_offsets.append(request.url.params["offset"])
        return httpx.Response(200, json=responses.pop(0))

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client)
        pages = list(client.iter_pages())

    assert observed_offsets == ["0", "2"]
    assert [page.record_count for page in pages] == [2, 1]
    assert [record["id"] for page in pages for record in page.records] == ["one", "two", "three"]


def test_retryable_status_is_retried_with_retry_after_without_exposing_key() -> None:
    responses = [
        httpx.Response(429, headers={"retry-after": "1.5"}),
        httpx.Response(200, json={"records": [], "total": 0}),
    ]
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client, sleep=delays.append)
        page = client.fetch_page(0)

    assert page.record_count == 0
    assert delays == [1.5]


def test_retryable_network_error_is_retried_with_exponential_backoff() -> None:
    calls = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectTimeout("timed out", request=request)
        return httpx.Response(200, json={"records": [], "total": 0})

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client, sleep=delays.append)
        page = client.fetch_page(0)

    assert page.total == 0
    assert calls == 2
    assert delays == [0.25]


def test_non_retryable_error_has_safe_message() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid key"})

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client)
        with pytest.raises(DataGovRequestError) as error:
            client.fetch_page(0)

    assert "HTTP 401" in str(error.value)
    assert "test-api-key" not in str(error.value)
    assert "invalid key" not in str(error.value)


def test_malformed_payload_fails_without_silently_dropping_source_data() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client)
        with pytest.raises(DataGovPayloadError, match="invalid JSON"):
            client.fetch_page(0)


def test_pagination_fails_when_total_claims_records_but_page_is_empty() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"records": [], "total": 5})

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client)
        with pytest.raises(DataGovPaginationError, match="empty page"):
            list(client.iter_pages())


def test_missing_api_key_fails_before_any_request() -> None:
    settings = load_settings(environ={})

    with pytest.raises(ConfigurationError, match="DATA_GOV_API_KEY"):
        DataGovClient(settings)


@pytest.mark.parametrize("offset", [-1, True, 1.5])
def test_invalid_offsets_are_rejected(offset: object) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("A request should not be sent for an invalid offset.")

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client)
        with pytest.raises(ValueError, match="non-negative integer"):
            client.fetch_page(offset)  # type: ignore[arg-type]


def test_records_must_be_json_objects() -> None:
    raw_response = json.dumps({"records": ["not-a-record"], "total": 1}).encode()

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw_response)

    with _mock_client(handler) as http_client:
        client = DataGovClient(_settings(), client=http_client)
        with pytest.raises(DataGovPayloadError, match="JSON objects"):
            client.fetch_page(0)
