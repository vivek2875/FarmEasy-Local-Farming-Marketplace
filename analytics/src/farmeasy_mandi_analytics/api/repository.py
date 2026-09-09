"""Parameterized PostgreSQL read models behind the FarmEasy analytics API."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date
from typing import Protocol

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from farmeasy_mandi_analytics.config import Settings
from farmeasy_mandi_analytics.validate.standardize import normalize_name_key

from .models import AnalyticsFilters, AnalyticsPage, PaginationRequest

LOGGER = logging.getLogger(__name__)


class AnalyticsRepositoryError(RuntimeError):
    """Raised when an analytics read cannot safely complete."""


class AnalyticsRepositoryProtocol(Protocol):
    """Small interface that lets API tests avoid a PostgreSQL dependency."""

    def list_commodities(
        self, *, search: str | None, pagination: PaginationRequest
    ) -> AnalyticsPage: ...

    def list_markets(
        self,
        *,
        filters: AnalyticsFilters,
        search: str | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage: ...

    def list_latest_prices(
        self,
        *,
        filters: AnalyticsFilters,
        include_suspicious: bool,
        pagination: PaginationRequest,
    ) -> AnalyticsPage: ...

    def list_price_trends(
        self,
        *,
        filters: AnalyticsFilters,
        date_from: date | None,
        date_to: date | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage: ...

    def compare_markets(
        self,
        *,
        filters: AnalyticsFilters,
        include_suspicious: bool,
        pagination: PaginationRequest,
    ) -> AnalyticsPage: ...

    def list_volatility(
        self,
        *,
        commodity: str | None,
        min_observation_count: int,
        pagination: PaginationRequest,
    ) -> AnalyticsPage: ...

    def list_data_quality(
        self,
        *,
        source_name: str | None,
        run_status: str | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage: ...


_OBSERVATION_FILTER_TEMPLATE = """
    (:state IS NULL OR {alias}.state_normalized = :state)
    AND (:district IS NULL OR {alias}.district_normalized = :district)
    AND (:market IS NULL OR {alias}.market_normalized = :market)
    AND (:commodity IS NULL OR {alias}.commodity_normalized = :commodity)
    AND (:variety IS NULL OR {alias}.variety_normalized = :variety)
    AND (:grade IS NULL OR {alias}.grade_normalized = :grade)
"""


def _observation_filters(alias: str, *, include_quality_filter: bool = False) -> str:
    """Render only a controlled table alias; all values remain SQL bind parameters."""
    if alias not in {"p", "t"}:
        raise ValueError(f"Unsupported analytics view alias: {alias}.")
    filters = _OBSERVATION_FILTER_TEMPLATE.format(alias=alias)
    if include_quality_filter:
        filters += f"\n    AND (:include_suspicious OR {alias}.quality_status <> 'suspicious')"
    return filters


def _normalised_like_pattern(value: str | None) -> str | None:
    """Normalize then escape a partial search before it becomes a bound parameter."""
    normalized = normalize_name_key(value)
    if not normalized:
        return None
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class AnalyticsRepository:
    """Read-only access to governed analytics views, never FarmEasy MySQL tables."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @classmethod
    def from_settings(cls, settings: Settings) -> AnalyticsRepository:
        """Create a small, health-checked pool against the dedicated PostgreSQL URL."""
        return cls(
            create_engine(
                settings.require_database_url(),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=5,
            )
        )

    def close(self) -> None:
        """Release idle pooled connections during controlled shutdown."""
        self.engine.dispose()

    def _fetch_page(
        self,
        *,
        select_sql: str,
        count_sql: str,
        parameters: Mapping[str, object],
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        base_parameters = dict(parameters)
        page_parameters = {
            **base_parameters,
            "limit": pagination.limit,
            "offset": pagination.offset,
        }
        try:
            with self.engine.connect() as connection:
                total = connection.execute(text(count_sql), base_parameters).scalar_one()
                rows = connection.execute(text(select_sql), page_parameters).mappings().all()
        except SQLAlchemyError as error:
            LOGGER.warning("Analytics query failed; database details are intentionally redacted.")
            raise AnalyticsRepositoryError("Analytics data is temporarily unavailable.") from error

        return AnalyticsPage(
            items=[dict(row) for row in rows],
            total=int(total),
            limit=pagination.limit,
            offset=pagination.offset,
        )

    def list_commodities(
        self, *, search: str | None, pagination: PaginationRequest
    ) -> AnalyticsPage:
        source_sql = r"""
            FROM analytics.vw_dashboard_volatility AS v
            WHERE (
                :search_pattern IS NULL
                OR v.commodity_normalized LIKE :search_pattern ESCAPE '\'
            )
        """
        return self._fetch_page(
            select_sql="""
                SELECT
                    v.commodity_key, v.commodity_name, v.commodity_normalized,
                    v.variety_name, v.variety_normalized, v.grade_name, v.grade_normalized,
                    v.price_unit, v.first_reporting_date, v.latest_reporting_date,
                    v.observation_count, v.reporting_mandi_count
            """
            + source_sql
            + """
                ORDER BY v.commodity_name, v.variety_name, v.grade_name
                LIMIT :limit OFFSET :offset
            """,
            count_sql="SELECT COUNT(*) " + source_sql,
            parameters={"search_pattern": _normalised_like_pattern(search)},
            pagination=pagination,
        )

    def list_markets(
        self,
        *,
        filters: AnalyticsFilters,
        search: str | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        source_sql = r"""
            FROM analytics.vw_dashboard_market_freshness AS m
            WHERE (:state IS NULL OR m.state_normalized = :state)
              AND (:district IS NULL OR m.district_normalized = :district)
              AND (:market IS NULL OR m.market_normalized = :market)
              AND (
                    :search_pattern IS NULL
                    OR m.market_normalized LIKE :search_pattern ESCAPE '\'
              )
        """
        return self._fetch_page(
            select_sql="""
                SELECT
                    m.state_name, m.state_normalized, m.district_name, m.district_normalized,
                    m.market_key, m.market_name, m.market_normalized, m.latest_market_date,
                    m.days_since_latest_report, m.observation_count,
                    m.flagged_stale_in_latest_run
            """
            + source_sql
            + """
                ORDER BY m.state_name, m.district_name, m.market_name
                LIMIT :limit OFFSET :offset
            """,
            count_sql="SELECT COUNT(*) " + source_sql,
            parameters={
                **filters.as_parameters(),
                "search_pattern": _normalised_like_pattern(search),
            },
            pagination=pagination,
        )

    def list_latest_prices(
        self,
        *,
        filters: AnalyticsFilters,
        include_suspicious: bool,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        source_sql = (
            "FROM analytics.vw_dashboard_latest_market_comparison AS p WHERE "
            + _observation_filters("p", include_quality_filter=True)
        )
        return self._fetch_page(
            select_sql="""
                SELECT
                    p.market_date,
                    p.state_name, p.state_normalized, p.district_name, p.district_normalized,
                    p.market_key, p.market_name, p.market_normalized,
                    p.commodity_key, p.commodity_name, p.commodity_normalized,
                    p.variety_name, p.variety_normalized, p.grade_name, p.grade_normalized,
                    p.min_price, p.max_price, p.modal_price, p.price_unit,
                    p.price_spread, p.price_spread_pct, p.quality_status,
                    p.state_average_modal_price, p.district_average_modal_price,
                    p.difference_from_state_average, p.difference_from_district_average,
                    p.state_modal_price_rank
            """
            + source_sql
            + """
                ORDER BY p.modal_price DESC, p.market_date DESC, p.market_name
                LIMIT :limit OFFSET :offset
            """,
            count_sql="SELECT COUNT(*) " + source_sql,
            parameters={
                **filters.as_parameters(),
                "include_suspicious": include_suspicious,
            },
            pagination=pagination,
        )

    def list_price_trends(
        self,
        *,
        filters: AnalyticsFilters,
        date_from: date | None,
        date_to: date | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        source_sql = (
            "FROM analytics.vw_dashboard_price_trends AS t WHERE "
            + _observation_filters("t")
            + """
                AND (:date_from IS NULL OR t.market_date >= :date_from)
                AND (:date_to IS NULL OR t.market_date <= :date_to)
            """
        )
        return self._fetch_page(
            select_sql="""
                SELECT
                    t.date_key, t.market_date,
                    t.state_name, t.state_normalized, t.district_name, t.district_normalized,
                    t.market_key, t.market_name, t.market_normalized,
                    t.commodity_key, t.commodity_name, t.commodity_normalized,
                    t.variety_name, t.variety_normalized, t.grade_name, t.grade_normalized,
                    t.price_unit, t.avg_min_price, t.avg_max_price, t.avg_modal_price,
                    t.avg_price_spread, t.avg_price_spread_pct, t.observation_count,
                    t.suspicious_observation_count, t.modal_price_7d_moving_avg,
                    t.modal_price_30d_moving_avg, t.prior_reporting_day_modal_price
            """
            + source_sql
            + """
                ORDER BY t.market_date, t.market_name, t.commodity_name
                LIMIT :limit OFFSET :offset
            """,
            count_sql="SELECT COUNT(*) " + source_sql,
            parameters={
                **filters.as_parameters(),
                "date_from": date_from,
                "date_to": date_to,
            },
            pagination=pagination,
        )

    def compare_markets(
        self,
        *,
        filters: AnalyticsFilters,
        include_suspicious: bool,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        if filters.commodity is None:
            raise ValueError("A commodity filter is required when comparing markets.")
        return self.list_latest_prices(
            filters=filters,
            include_suspicious=include_suspicious,
            pagination=pagination,
        )

    def list_volatility(
        self,
        *,
        commodity: str | None,
        min_observation_count: int,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        source_sql = r"""
            FROM analytics.vw_dashboard_volatility AS v
            WHERE (:commodity IS NULL OR v.commodity_normalized = :commodity)
              AND v.observation_count >= :min_observation_count
        """
        return self._fetch_page(
            select_sql="""
                SELECT
                    v.commodity_key, v.commodity_name, v.commodity_normalized,
                    v.variety_name, v.variety_normalized, v.grade_name, v.grade_normalized,
                    v.price_unit, v.first_reporting_date, v.latest_reporting_date,
                    v.observation_count, v.reporting_mandi_count, v.average_modal_price,
                    v.modal_price_stddev, v.modal_price_coefficient_of_variation_pct,
                    v.minimum_modal_price, v.maximum_modal_price, v.average_price_spread,
                    v.average_price_spread_pct, v.suspicious_observation_count
            """
            + source_sql
            + """
                ORDER BY v.modal_price_coefficient_of_variation_pct DESC NULLS LAST,
                    v.observation_count DESC, v.commodity_name
                LIMIT :limit OFFSET :offset
            """,
            count_sql="SELECT COUNT(*) " + source_sql,
            parameters={
                "commodity": commodity,
                "min_observation_count": min_observation_count,
            },
            pagination=pagination,
        )

    def list_data_quality(
        self,
        *,
        source_name: str | None,
        run_status: str | None,
        pagination: PaginationRequest,
    ) -> AnalyticsPage:
        source_sql = """
            FROM analytics.vw_dashboard_data_quality AS q
            WHERE (:source_name IS NULL OR q.source_name = :source_name)
              AND (:run_status IS NULL OR q.status = :run_status)
        """
        return self._fetch_page(
            select_sql="""
                SELECT
                    q.run_id, q.source_name, q.status, q.started_at, q.completed_at,
                    q.raw_rows_received, q.valid_rows_loaded, q.invalid_rows_rejected,
                    q.duplicates_removed, q.conflicting_observation_count,
                    q.suspicious_price_count, q.missing_reporting_date_count,
                    q.stale_market_count, q.data_freshness_date, q.fact_rows_affected,
                    q.quality_issues_logged, q.logged_issue_count, q.error_issue_count,
                    q.warning_issue_count, q.duplicate_issue_count,
                    q.conflicting_issue_count, q.suspicious_price_issue_count,
                    q.stale_market_issue_count, q.missing_reporting_date_issue_count
            """
            + source_sql
            + """
                ORDER BY q.started_at DESC
                LIMIT :limit OFFSET :offset
            """,
            count_sql="SELECT COUNT(*) " + source_sql,
            parameters={"source_name": source_name, "run_status": run_status},
            pagination=pagination,
        )
