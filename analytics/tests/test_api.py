"""Integration-style tests for the public FarmEasy analytics API contract."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from farmeasy_mandi_analytics.api.app import BEST_MANDI_ADVISORY, create_app
from farmeasy_mandi_analytics.api.models import AnalyticsFilters, AnalyticsPage, PaginationRequest
from farmeasy_mandi_analytics.api.rate_limit import SlidingWindowRateLimiter
from farmeasy_mandi_analytics.api.repository import AnalyticsRepositoryError
from farmeasy_mandi_analytics.config import load_settings


class FakeAnalyticsRepository:
    """Deterministic read-model double; API tests do not need PostgreSQL."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail_on = fail_on

    @staticmethod
    def _page(item: dict[str, Any], pagination: PaginationRequest) -> AnalyticsPage:
        return AnalyticsPage(
            items=[item],
            total=1,
            limit=pagination.limit,
            offset=pagination.offset,
        )

    def _record(self, method: str, **arguments: Any) -> None:
        self.calls.append((method, arguments))
        if self.fail_on == method:
            raise AnalyticsRepositoryError("internal database password must never be returned")

    def list_commodities(
        self, *, search: str | None, pagination: PaginationRequest
    ) -> AnalyticsPage:
        self._record("list_commodities", search=search, pagination=pagination)
        return self._page(
            {
                "commodity_key": 1,
                "commodity_name": "Tomato",
                "commodity_normalized": "tomato",
                "variety_name": "Other",
                "variety_normalized": "other",
                "grade_name": "FAQ",
                "grade_normalized": "faq",
                "price_unit": "INR/quintal",
                "first_reporting_date": date(2026, 9, 1),
                "latest_reporting_date": date(2026, 9, 8),
                "observation_count": 8,
                "reporting_mandi_count": 2,
            },
            pagination,
        )

    def list_markets(
        self,
        *,
        filters: AnalyticsFilters,
        search: str | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        self._record(
            "list_markets",
            filters=filters,
            search=search,
            pagination=pagination,
        )
        return self._page(
            {
                "state_name": "Karnataka",
                "state_normalized": "karnataka",
                "district_name": "Mysuru",
                "district_normalized": "mysuru",
                "market_key": 1,
                "market_name": "Mysuru APMC",
                "market_normalized": "mysuru apmc",
                "latest_market_date": date(2026, 9, 8),
                "days_since_latest_report": 1,
                "observation_count": 8,
                "flagged_stale_in_latest_run": False,
            },
            pagination,
        )

    @staticmethod
    def _latest_price_item() -> dict[str, Any]:
        return {
            "market_date": date(2026, 9, 8),
            "state_name": "Karnataka",
            "state_normalized": "karnataka",
            "district_name": "Mysuru",
            "district_normalized": "mysuru",
            "market_key": 1,
            "market_name": "Mysuru APMC",
            "market_normalized": "mysuru apmc",
            "commodity_key": 1,
            "commodity_name": "Tomato",
            "commodity_normalized": "tomato",
            "variety_name": "Other",
            "variety_normalized": "other",
            "grade_name": "FAQ",
            "grade_normalized": "faq",
            "min_price": Decimal("1000.00"),
            "max_price": Decimal("1800.00"),
            "modal_price": Decimal("1400.00"),
            "price_unit": "INR/quintal",
            "price_spread": Decimal("800.00"),
            "price_spread_pct": Decimal("57.1429"),
            "quality_status": "valid",
            "state_average_modal_price": Decimal("1350.00"),
            "district_average_modal_price": Decimal("1375.00"),
            "difference_from_state_average": Decimal("50.00"),
            "difference_from_district_average": Decimal("25.00"),
            "state_modal_price_rank": 1,
        }

    def list_latest_prices(
        self,
        *,
        filters: AnalyticsFilters,
        include_suspicious: bool,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        self._record(
            "list_latest_prices",
            filters=filters,
            include_suspicious=include_suspicious,
            pagination=pagination,
        )
        return self._page(self._latest_price_item(), pagination)

    def list_price_trends(
        self,
        *,
        filters: AnalyticsFilters,
        date_from: date | None,
        date_to: date | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        self._record(
            "list_price_trends",
            filters=filters,
            date_from=date_from,
            date_to=date_to,
            pagination=pagination,
        )
        return self._page(
            {
                "date_key": 20260908,
                "market_date": date(2026, 9, 8),
                "state_name": "Karnataka",
                "state_normalized": "karnataka",
                "district_name": "Mysuru",
                "district_normalized": "mysuru",
                "market_key": 1,
                "market_name": "Mysuru APMC",
                "market_normalized": "mysuru apmc",
                "commodity_key": 1,
                "commodity_name": "Tomato",
                "commodity_normalized": "tomato",
                "variety_name": "Other",
                "variety_normalized": "other",
                "grade_name": "FAQ",
                "grade_normalized": "faq",
                "price_unit": "INR/quintal",
                "avg_min_price": Decimal("1000.00"),
                "avg_max_price": Decimal("1800.00"),
                "avg_modal_price": Decimal("1400.00"),
                "avg_price_spread": Decimal("800.00"),
                "avg_price_spread_pct": Decimal("57.1429"),
                "observation_count": 1,
                "suspicious_observation_count": 0,
                "modal_price_7d_moving_avg": Decimal("1360.00"),
                "modal_price_30d_moving_avg": Decimal("1320.00"),
                "prior_reporting_day_modal_price": Decimal("1380.00"),
            },
            pagination,
        )

    def compare_markets(
        self,
        *,
        filters: AnalyticsFilters,
        include_suspicious: bool,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        self._record(
            "compare_markets",
            filters=filters,
            include_suspicious=include_suspicious,
            pagination=pagination,
        )
        return self._page(self._latest_price_item(), pagination)

    def list_volatility(
        self,
        *,
        commodity: str | None,
        min_observation_count: int,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        self._record(
            "list_volatility",
            commodity=commodity,
            min_observation_count=min_observation_count,
            pagination=pagination,
        )
        return self._page(
            {
                "commodity_key": 1,
                "commodity_name": "Tomato",
                "commodity_normalized": "tomato",
                "variety_name": "Other",
                "variety_normalized": "other",
                "grade_name": "FAQ",
                "grade_normalized": "faq",
                "price_unit": "INR/quintal",
                "first_reporting_date": date(2026, 9, 1),
                "latest_reporting_date": date(2026, 9, 8),
                "observation_count": 8,
                "reporting_mandi_count": 2,
                "average_modal_price": Decimal("1350.00"),
                "modal_price_stddev": Decimal("90.00"),
                "modal_price_coefficient_of_variation_pct": Decimal("6.67"),
                "minimum_modal_price": Decimal("1200.00"),
                "maximum_modal_price": Decimal("1500.00"),
                "average_price_spread": Decimal("700.00"),
                "average_price_spread_pct": Decimal("51.85"),
                "suspicious_observation_count": 0,
            },
            pagination,
        )

    def list_data_quality(
        self,
        *,
        source_name: str | None,
        run_status: str | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        self._record(
            "list_data_quality",
            source_name=source_name,
            run_status=run_status,
            pagination=pagination,
        )
        return self._page(
            {
                "run_id": "test-run-1",
                "source_name": "data_gov_current_mandi",
                "status": "succeeded",
                "started_at": datetime(2026, 9, 8, 8, tzinfo=UTC),
                "completed_at": datetime(2026, 9, 8, 8, 1, tzinfo=UTC),
                "raw_rows_received": 10,
                "valid_rows_loaded": 8,
                "invalid_rows_rejected": 1,
                "duplicates_removed": 1,
                "conflicting_observation_count": 0,
                "suspicious_price_count": 1,
                "missing_reporting_date_count": 1,
                "stale_market_count": 0,
                "data_freshness_date": date(2026, 9, 8),
                "fact_rows_affected": 8,
                "quality_issues_logged": 3,
                "logged_issue_count": 3,
                "error_issue_count": 1,
                "warning_issue_count": 2,
                "duplicate_issue_count": 1,
                "conflicting_issue_count": 0,
                "suspicious_price_issue_count": 1,
                "stale_market_issue_count": 0,
                "missing_reporting_date_issue_count": 1,
            },
            pagination,
        )


@pytest.fixture
def repository() -> FakeAnalyticsRepository:
    return FakeAnalyticsRepository()


@pytest.fixture
def client(repository: FakeAnalyticsRepository) -> TestClient:
    application = create_app(
        repository,
        rate_limiter=SlidingWindowRateLimiter(limit=100),
    )
    with TestClient(application) as test_client:
        yield test_client


@pytest.mark.parametrize(
    ("path", "expected_field"),
    [
        ("/api/analytics/commodities", "commodity_name"),
        ("/api/analytics/markets", "market_name"),
        ("/api/analytics/prices/latest", "modal_price"),
        ("/api/analytics/prices/trends", "modal_price_7d_moving_avg"),
        ("/api/analytics/markets/compare?commodity=tomato", "state_modal_price_rank"),
        ("/api/analytics/volatility", "modal_price_coefficient_of_variation_pct"),
        ("/api/analytics/data-quality", "raw_rows_received"),
    ],
)
def test_read_endpoints_return_typed_paginated_contracts(
    client: TestClient,
    path: str,
    expected_field: str,
) -> None:
    response = client.get(path)

    assert response.status_code == 200
    payload = response.json()
    assert payload["pagination"] == {"limit": 50, "offset": 0, "total": 1}
    assert expected_field in payload["data"][0]
    if path.startswith("/api/analytics/markets/compare"):
        assert payload["advisory"] == BEST_MANDI_ADVISORY


def test_filters_are_normalized_before_reaching_the_repository(
    client: TestClient,
    repository: FakeAnalyticsRepository,
) -> None:
    response = client.get(
        "/api/analytics/markets",
        params={
            "state": "  KARNATAKA ",
            "market": "Mysuru APMC",
            "search": "  mysuru ",
            "limit": 1,
            "offset": 2,
        },
    )

    assert response.status_code == 200
    method, arguments = repository.calls[-1]
    assert method == "list_markets"
    assert arguments["filters"] == AnalyticsFilters(state="karnataka", market="mysuru apmc")
    assert arguments["search"] == "mysuru"
    assert arguments["pagination"] == PaginationRequest(limit=1, offset=2)


def test_invalid_query_parameters_use_the_consistent_error_envelope(client: TestClient) -> None:
    invalid_limit = client.get("/api/analytics/prices/latest?limit=0")
    missing_commodity = client.get("/api/analytics/markets/compare")
    inverted_dates = client.get(
        "/api/analytics/prices/trends?date_from=2026-09-08&date_to=2026-09-01"
    )

    assert invalid_limit.status_code == 422
    assert invalid_limit.json()["error"]["code"] == "invalid_request"
    assert missing_commodity.status_code == 422
    assert missing_commodity.json()["error"]["code"] == "invalid_request"
    assert inverted_dates.status_code == 422
    assert inverted_dates.json()["error"]["message"] == "date_from must be on or before date_to."


def test_warehouse_failure_does_not_expose_internal_error_details() -> None:
    application = create_app(
        FakeAnalyticsRepository(fail_on="list_latest_prices"),
        rate_limiter=SlidingWindowRateLimiter(limit=100),
    )
    with TestClient(application) as client:
        response = client.get("/api/analytics/prices/latest")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "analytics_unavailable"
    assert "password" not in response.text.lower()


def test_rate_limiter_returns_a_retry_contract() -> None:
    application = create_app(
        FakeAnalyticsRepository(),
        rate_limiter=SlidingWindowRateLimiter(limit=2),
    )
    with TestClient(application) as client:
        assert client.get("/api/analytics/commodities").status_code == 200
        assert client.get("/api/analytics/commodities").status_code == 200
        throttled = client.get("/api/analytics/commodities")

    assert throttled.status_code == 429
    assert throttled.headers["Retry-After"]
    assert throttled.json()["error"]["code"] == "rate_limited"


def test_configured_service_token_blocks_unauthenticated_requests(tmp_path) -> None:
    settings = load_settings(
        environ={"FARMEASY_ANALYTICS_API_ACCESS_TOKEN": "portfolio-test-token"},
        project_root=tmp_path,
    )
    application = create_app(
        FakeAnalyticsRepository(),
        settings=settings,
        rate_limiter=SlidingWindowRateLimiter(limit=100),
    )

    with TestClient(application) as client:
        rejected = client.get("/api/analytics/commodities")
        allowed = client.get(
            "/api/analytics/commodities",
            headers={"X-Analytics-Token": "portfolio-test-token"},
        )

    assert rejected.status_code == 401
    assert rejected.json()["error"]["code"] == "authentication_required"
    assert allowed.status_code == 200
