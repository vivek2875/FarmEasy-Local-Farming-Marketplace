"""Application factory for the decoupled, read-only FarmEasy analytics API."""

# ruff: noqa: B008

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from typing import cast

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from farmeasy_mandi_analytics.config import Settings, load_settings
from farmeasy_mandi_analytics.validate.standardize import normalize_name_key

from .models import (
    AnalyticsFilters,
    AnalyticsPage,
    CommodityPage,
    DataQualityPage,
    ErrorDetail,
    ErrorPayload,
    ErrorResponse,
    LatestPricePage,
    MarketComparisonPage,
    MarketPage,
    PaginationMetadata,
    PaginationRequest,
    PriceTrendPage,
    VolatilityPage,
)
from .rate_limit import AnalyticsRateLimitMiddleware, SlidingWindowRateLimiter
from .repository import (
    AnalyticsRepository,
    AnalyticsRepositoryError,
    AnalyticsRepositoryProtocol,
)

LOGGER = logging.getLogger(__name__)
API_PREFIX = "/api/analytics"
BEST_MANDI_ADVISORY = (
    "A higher reported modal price is not guaranteed profit. Compare transport distance and "
    "cost, quality/grade, commissions, market fees, buyer demand, and available quantity "
    "before choosing a mandi."
)


class ApiRequestError(ValueError):
    """Expected client error that uses the stable API error envelope."""

    def __init__(self, message: str, *, details: list[ErrorDetail] | None = None) -> None:
        super().__init__(message)
        self.details = details


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorPayload(code=code, message=message, details=details),
    ).model_dump(mode="json", exclude_none=True)
    return JSONResponse(status_code=status_code, content=payload)


def _validation_details(error: RequestValidationError) -> list[ErrorDetail]:
    details: list[ErrorDetail] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", ("request",)))
        details.append(
            ErrorDetail(
                field=location,
                message=str(item.get("msg", "Invalid value.")),
            )
        )
    return details


def _build_filters(
    *,
    state: str | None = None,
    district: str | None = None,
    market: str | None = None,
    commodity: str | None = None,
    variety: str | None = None,
    grade: str | None = None,
) -> AnalyticsFilters:
    return AnalyticsFilters.from_values(
        state=state,
        district=district,
        market=market,
        commodity=commodity,
        variety=variety,
        grade=grade,
    )


def pagination(
    limit: int = Query(50, ge=1, le=500, description="Maximum rows to return."),
    offset: int = Query(0, ge=0, description="Zero-based number of rows to skip."),
) -> PaginationRequest:
    """Provide a consistent bounded pagination contract for every collection."""
    return PaginationRequest(limit=limit, offset=offset)


def common_filters(
    state: str | None = Query(None, min_length=1, max_length=128, pattern=r".*\S.*"),
    district: str | None = Query(None, min_length=1, max_length=128, pattern=r".*\S.*"),
    market: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
    commodity: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
    variety: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
    grade: str | None = Query(None, min_length=1, max_length=80, pattern=r".*\S.*"),
) -> AnalyticsFilters:
    """Normalize user filters to the same keys used by the analytical dimensions."""
    return _build_filters(
        state=state,
        district=district,
        market=market,
        commodity=commodity,
        variety=variety,
        grade=grade,
    )


def comparison_filters(
    commodity: str = Query(..., min_length=1, max_length=160, pattern=r".*\S.*"),
    state: str | None = Query(None, min_length=1, max_length=128, pattern=r".*\S.*"),
    district: str | None = Query(None, min_length=1, max_length=128, pattern=r".*\S.*"),
    market: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
    variety: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
    grade: str | None = Query(None, min_length=1, max_length=80, pattern=r".*\S.*"),
) -> AnalyticsFilters:
    """Require a commodity before a price ranking can be meaningful."""
    return _build_filters(
        state=state,
        district=district,
        market=market,
        commodity=commodity,
        variety=variety,
        grade=grade,
    )


def date_range(
    date_from: date | None = Query(None, description="Inclusive ISO start date."),
    date_to: date | None = Query(None, description="Inclusive ISO end date."),
) -> tuple[date | None, date | None]:
    """Reject an inverted trend date range before querying PostgreSQL."""
    if date_from and date_to and date_from > date_to:
        raise ApiRequestError(
            "date_from must be on or before date_to.",
            details=[
                ErrorDetail(
                    field="query.date_from",
                    message="Use a date on or before query.date_to.",
                )
            ],
        )
    return date_from, date_to


def get_repository(request: Request) -> AnalyticsRepositoryProtocol:
    """Retrieve the repository injected into the application factory."""
    return cast(AnalyticsRepositoryProtocol, request.app.state.analytics_repository)


def _page_response(page: AnalyticsPage) -> dict[str, object]:
    return {
        "data": [dict(item) for item in page.items],
        "pagination": PaginationMetadata(
            limit=page.limit,
            offset=page.offset,
            total=page.total,
        ).model_dump(),
    }


def create_app(
    repository: AnalyticsRepositoryProtocol | None = None,
    *,
    settings: Settings | None = None,
    rate_limiter: SlidingWindowRateLimiter | None = None,
) -> FastAPI:
    """Create a testable API without coupling it to FarmEasy PHP sessions or tables."""
    resolved_settings = settings
    if repository is None:
        resolved_settings = resolved_settings or load_settings()
        repository = AnalyticsRepository.from_settings(resolved_settings)

    if rate_limiter is None:
        configured_limit = (
            resolved_settings.api_rate_limit_per_minute if resolved_settings is not None else 120
        )
        rate_limiter = SlidingWindowRateLimiter(limit=configured_limit)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(repository, "close", None)
        if callable(close):
            close()

    application = FastAPI(
        title="FarmEasy Mandi Price and Supply Intelligence API",
        version="1.0.0",
        description=(
            "Read-only analytical endpoints backed by the dedicated FarmEasy PostgreSQL "
            "warehouse. They never access marketplace user, order, or credential tables."
        ),
        lifespan=lifespan,
    )
    application.state.analytics_repository = repository
    application.add_middleware(
        AnalyticsRateLimitMiddleware,
        limiter=rate_limiter,
        access_token=resolved_settings.api_access_token if resolved_settings else None,
    )
    if resolved_settings and resolved_settings.api_allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.api_allowed_origins),
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Accept", "Content-Type"],
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        return _error_response(
            status_code=422,
            code="invalid_request",
            message="Request validation failed.",
            details=_validation_details(error),
        )

    @application.exception_handler(ApiRequestError)
    async def handle_api_request_error(_: Request, error: ApiRequestError) -> JSONResponse:
        return _error_response(
            status_code=422,
            code="invalid_request",
            message=str(error),
            details=error.details,
        )

    @application.exception_handler(AnalyticsRepositoryError)
    async def handle_repository_error(_: Request, error: AnalyticsRepositoryError) -> JSONResponse:
        LOGGER.warning("Analytics API request could not read its warehouse: %s", error)
        return _error_response(
            status_code=503,
            code="analytics_unavailable",
            message="Analytics data is temporarily unavailable. Try again later.",
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(_: Request, error: Exception) -> JSONResponse:
        LOGGER.exception("Unexpected FarmEasy analytics API error", exc_info=error)
        return _error_response(
            status_code=500,
            code="internal_error",
            message="An unexpected server error occurred.",
        )

    @application.get(
        f"{API_PREFIX}/commodities",
        response_model=CommodityPage,
        responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        tags=["catalogue"],
    )
    def list_commodities(
        search: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
        page: PaginationRequest = Depends(pagination),
        analytics_repository: AnalyticsRepositoryProtocol = Depends(get_repository),
    ) -> dict[str, object]:
        return _page_response(
            analytics_repository.list_commodities(
                search=normalize_name_key(search),
                pagination=page,
            )
        )

    @application.get(
        f"{API_PREFIX}/markets",
        response_model=MarketPage,
        responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        tags=["catalogue"],
    )
    def list_markets(
        search: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
        filters: AnalyticsFilters = Depends(common_filters),
        page: PaginationRequest = Depends(pagination),
        analytics_repository: AnalyticsRepositoryProtocol = Depends(get_repository),
    ) -> dict[str, object]:
        return _page_response(
            analytics_repository.list_markets(
                filters=filters,
                search=normalize_name_key(search),
                pagination=page,
            )
        )

    @application.get(
        f"{API_PREFIX}/prices/latest",
        response_model=LatestPricePage,
        responses={
            422: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
        tags=["prices"],
    )
    def list_latest_prices(
        include_suspicious: bool = Query(
            False,
            description="Include price observations flagged for review.",
        ),
        filters: AnalyticsFilters = Depends(common_filters),
        page: PaginationRequest = Depends(pagination),
        analytics_repository: AnalyticsRepositoryProtocol = Depends(get_repository),
    ) -> dict[str, object]:
        return _page_response(
            analytics_repository.list_latest_prices(
                filters=filters,
                include_suspicious=include_suspicious,
                pagination=page,
            )
        )

    @application.get(
        f"{API_PREFIX}/prices/trends",
        response_model=PriceTrendPage,
        responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        tags=["prices"],
    )
    def list_price_trends(
        selected_dates: tuple[date | None, date | None] = Depends(date_range),
        filters: AnalyticsFilters = Depends(common_filters),
        page: PaginationRequest = Depends(pagination),
        analytics_repository: AnalyticsRepositoryProtocol = Depends(get_repository),
    ) -> dict[str, object]:
        date_from, date_to = selected_dates
        return _page_response(
            analytics_repository.list_price_trends(
                filters=filters,
                date_from=date_from,
                date_to=date_to,
                pagination=page,
            )
        )

    @application.get(
        f"{API_PREFIX}/markets/compare",
        response_model=MarketComparisonPage,
        responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        tags=["comparisons"],
    )
    def compare_markets(
        include_suspicious: bool = Query(
            False,
            description="Include price observations flagged for review.",
        ),
        filters: AnalyticsFilters = Depends(comparison_filters),
        page: PaginationRequest = Depends(pagination),
        analytics_repository: AnalyticsRepositoryProtocol = Depends(get_repository),
    ) -> dict[str, object]:
        return {
            "advisory": BEST_MANDI_ADVISORY,
            **_page_response(
                analytics_repository.compare_markets(
                    filters=filters,
                    include_suspicious=include_suspicious,
                    pagination=page,
                )
            ),
        }

    @application.get(
        f"{API_PREFIX}/volatility",
        response_model=VolatilityPage,
        responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        tags=["risk"],
    )
    def list_volatility(
        commodity: str | None = Query(None, min_length=1, max_length=160, pattern=r".*\S.*"),
        min_observation_count: int = Query(
            2,
            ge=2,
            le=1_000_000,
            description="Exclude commodity series with too little history.",
        ),
        page: PaginationRequest = Depends(pagination),
        analytics_repository: AnalyticsRepositoryProtocol = Depends(get_repository),
    ) -> dict[str, object]:
        return _page_response(
            analytics_repository.list_volatility(
                commodity=normalize_name_key(commodity),
                min_observation_count=min_observation_count,
                pagination=page,
            )
        )

    @application.get(
        f"{API_PREFIX}/data-quality",
        response_model=DataQualityPage,
        responses={422: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
        tags=["data quality"],
    )
    def list_data_quality(
        source_name: str | None = Query(None, min_length=1, max_length=128, pattern=r".*\S.*"),
        run_status: str | None = Query(
            None,
            pattern="^(running|succeeded|failed)$",
            description="Optional pipeline-run status.",
        ),
        page: PaginationRequest = Depends(pagination),
        analytics_repository: AnalyticsRepositoryProtocol = Depends(get_repository),
    ) -> dict[str, object]:
        return _page_response(
            analytics_repository.list_data_quality(
                source_name=normalize_name_key(source_name),
                run_status=run_status,
                pagination=page,
            )
        )

    return application


def create_production_app() -> FastAPI:
    """Uvicorn factory that reads environment configuration only at service start."""
    return create_app()
