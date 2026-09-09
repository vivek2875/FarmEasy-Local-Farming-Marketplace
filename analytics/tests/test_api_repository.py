"""Repository tests that prove public filters remain bind parameters."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from farmeasy_mandi_analytics.api.models import AnalyticsFilters, PaginationRequest
from farmeasy_mandi_analytics.api.repository import AnalyticsRepository


class _Result:
    def __init__(
        self, *, scalar: int | None = None, rows: list[dict[str, Any]] | None = None
    ) -> None:
        self.scalar = scalar
        self.rows = rows or []

    def scalar_one(self) -> int:
        assert self.scalar is not None
        return self.scalar

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class _RecordingConnection(AbstractContextManager):
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement, parameters: dict[str, Any]) -> _Result:
        self.calls.append((statement.text, dict(parameters)))
        if statement.text.lstrip().startswith("SELECT COUNT"):
            return _Result(scalar=0)
        return _Result(rows=[])

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class _RecordingEngine:
    def __init__(self) -> None:
        self.connection = _RecordingConnection()

    def connect(self) -> _RecordingConnection:
        return self.connection


def test_latest_price_query_keeps_untrusted_values_out_of_sql_text() -> None:
    engine = _RecordingEngine()
    repository = AnalyticsRepository(engine=engine)  # type: ignore[arg-type]
    harmful_value = "Karnataka'; DROP TABLE analytics.fact_mandi_prices; --"

    result = repository.list_latest_prices(
        filters=AnalyticsFilters.from_values(state=harmful_value, commodity="Tomato"),
        include_suspicious=False,
        pagination=PaginationRequest(limit=25, offset=50),
    )

    count_sql, count_parameters = engine.connection.calls[0]
    select_sql, select_parameters = engine.connection.calls[1]
    assert result.total == 0
    assert harmful_value not in count_sql
    assert harmful_value not in select_sql
    assert "DROP TABLE" not in select_sql
    assert count_parameters["state"] == harmful_value.casefold()
    assert select_parameters["limit"] == 25
    assert select_parameters["offset"] == 50
    assert select_parameters["include_suspicious"] is False
    assert "LIMIT :limit OFFSET :offset" in select_sql


def test_commodity_search_escapes_sql_like_wildcards() -> None:
    engine = _RecordingEngine()
    repository = AnalyticsRepository(engine=engine)  # type: ignore[arg-type]

    repository.list_commodities(
        search="Tomato_%",
        pagination=PaginationRequest(limit=10, offset=0),
    )

    _, parameters = engine.connection.calls[0]
    assert parameters["search_pattern"] == r"%tomato\_\%%"
