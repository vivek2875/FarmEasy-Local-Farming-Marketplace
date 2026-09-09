"""Typed public API contracts and query-value normalization."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

from farmeasy_mandi_analytics.validate.standardize import normalize_name_key


@dataclass(frozen=True, slots=True)
class PaginationRequest:
    """Bounded, zero-based pagination accepted by read endpoints."""

    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class AnalyticsFilters:
    """Normalized equality filters that match warehouse dimension keys."""

    state: str | None = None
    district: str | None = None
    market: str | None = None
    commodity: str | None = None
    variety: str | None = None
    grade: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        state: str | None = None,
        district: str | None = None,
        market: str | None = None,
        commodity: str | None = None,
        variety: str | None = None,
        grade: str | None = None,
    ) -> AnalyticsFilters:
        return cls(
            state=normalize_name_key(state),
            district=normalize_name_key(district),
            market=normalize_name_key(market),
            commodity=normalize_name_key(commodity),
            variety=normalize_name_key(variety),
            grade=normalize_name_key(grade),
        )

    def as_parameters(self) -> dict[str, str | None]:
        """Return only bound SQL parameters; never interpolate user input into SQL."""
        return {
            "state": self.state,
            "district": self.district,
            "market": self.market,
            "commodity": self.commodity,
            "variety": self.variety,
            "grade": self.grade,
        }


@dataclass(frozen=True, slots=True)
class AnalyticsPage:
    """Repository result before FastAPI serializes it into a response model."""

    items: list[Mapping[str, Any]]
    total: int
    limit: int
    offset: int


class ApiModel(BaseModel):
    """Base model that fails closed if a repository query drifts unexpectedly."""

    model_config = ConfigDict(extra="forbid")


class PaginationMetadata(ApiModel):
    limit: int
    offset: int
    total: int


class ErrorDetail(ApiModel):
    field: str
    message: str


class ErrorPayload(ApiModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(ApiModel):
    error: ErrorPayload


class CommodityItem(ApiModel):
    commodity_key: int
    commodity_name: str
    commodity_normalized: str
    variety_name: str
    variety_normalized: str
    grade_name: str
    grade_normalized: str
    price_unit: str
    first_reporting_date: date
    latest_reporting_date: date
    observation_count: int
    reporting_mandi_count: int


class CommodityPage(ApiModel):
    data: list[CommodityItem]
    pagination: PaginationMetadata


class MarketItem(ApiModel):
    state_name: str
    state_normalized: str
    district_name: str
    district_normalized: str
    market_key: int
    market_name: str
    market_normalized: str
    latest_market_date: date
    days_since_latest_report: int
    observation_count: int
    flagged_stale_in_latest_run: bool


class MarketPage(ApiModel):
    data: list[MarketItem]
    pagination: PaginationMetadata


class LatestPriceItem(ApiModel):
    market_date: date
    state_name: str
    state_normalized: str
    district_name: str
    district_normalized: str
    market_key: int
    market_name: str
    market_normalized: str
    commodity_key: int
    commodity_name: str
    commodity_normalized: str
    variety_name: str
    variety_normalized: str
    grade_name: str
    grade_normalized: str
    min_price: Decimal
    max_price: Decimal
    modal_price: Decimal
    price_unit: str
    price_spread: Decimal
    price_spread_pct: Decimal
    quality_status: str
    state_average_modal_price: Decimal | None
    district_average_modal_price: Decimal | None
    difference_from_state_average: Decimal | None
    difference_from_district_average: Decimal | None
    state_modal_price_rank: int


class LatestPricePage(ApiModel):
    data: list[LatestPriceItem]
    pagination: PaginationMetadata


class MarketComparisonPage(LatestPricePage):
    advisory: str


class PriceTrendItem(ApiModel):
    date_key: int
    market_date: date
    state_name: str
    state_normalized: str
    district_name: str
    district_normalized: str
    market_key: int
    market_name: str
    market_normalized: str
    commodity_key: int
    commodity_name: str
    commodity_normalized: str
    variety_name: str
    variety_normalized: str
    grade_name: str
    grade_normalized: str
    price_unit: str
    avg_min_price: Decimal
    avg_max_price: Decimal
    avg_modal_price: Decimal
    avg_price_spread: Decimal
    avg_price_spread_pct: Decimal
    observation_count: int
    suspicious_observation_count: int
    modal_price_7d_moving_avg: Decimal | None
    modal_price_30d_moving_avg: Decimal | None
    prior_reporting_day_modal_price: Decimal | None


class PriceTrendPage(ApiModel):
    data: list[PriceTrendItem]
    pagination: PaginationMetadata


class VolatilityItem(ApiModel):
    commodity_key: int
    commodity_name: str
    commodity_normalized: str
    variety_name: str
    variety_normalized: str
    grade_name: str
    grade_normalized: str
    price_unit: str
    first_reporting_date: date
    latest_reporting_date: date
    observation_count: int
    reporting_mandi_count: int
    average_modal_price: Decimal
    modal_price_stddev: Decimal | None
    modal_price_coefficient_of_variation_pct: Decimal | None
    minimum_modal_price: Decimal
    maximum_modal_price: Decimal
    average_price_spread: Decimal
    average_price_spread_pct: Decimal
    suspicious_observation_count: int


class VolatilityPage(ApiModel):
    data: list[VolatilityItem]
    pagination: PaginationMetadata


class DataQualityRunItem(ApiModel):
    run_id: str
    source_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    raw_rows_received: int
    valid_rows_loaded: int
    invalid_rows_rejected: int
    duplicates_removed: int
    conflicting_observation_count: int
    suspicious_price_count: int
    missing_reporting_date_count: int
    stale_market_count: int
    data_freshness_date: date | None
    fact_rows_affected: int
    quality_issues_logged: int
    logged_issue_count: int
    error_issue_count: int
    warning_issue_count: int
    duplicate_issue_count: int
    conflicting_issue_count: int
    suspicious_price_issue_count: int
    stale_market_issue_count: int
    missing_reporting_date_issue_count: int


class DataQualityPage(ApiModel):
    data: list[DataQualityRunItem]
    pagination: PaginationMetadata
