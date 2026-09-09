# FarmEasy analytics API

The analytics API is a small, read-only FastAPI service. It queries only the
dedicated PostgreSQL analytics schema and its governed dashboard views. It does
not connect to farmeasy.sql, the PHP application's MySQL/MariaDB database,
user accounts, transactions, or Data.gov.in credentials.

## Start locally

Complete a load-csv or load-api run and deploy the dashboard views first:

~~~powershell
.\.venv\Scripts\farmeasy-mandi.exe deploy-views
.\.venv\Scripts\uvicorn.exe farmeasy_mandi_analytics.api.app:create_production_app `
  --factory --host 127.0.0.1 --port 8000
~~~

The factory reads .env only when the service starts. It requires
FARMEASY_ANALYTICS_DATABASE_URL; use a PostgreSQL role that has SELECT on only
the published views, not the pipeline-writer role.

Interactive OpenAPI documentation is available locally at
http://127.0.0.1:8000/docs. It is useful for a trusted development environment;
do not expose it unintentionally on the public internet.

## Security and deployment

| Control | Implementation | Operational rule |
| --- | --- | --- |
| Database isolation | API uses the PostgreSQL analytics URL only. | Keep the legacy MySQL credentials separate. |
| Least privilege | API needs USAGE on schema analytics and SELECT on published views. | Do not give the API role DDL, write, or raw-receipt permissions. |
| Service token | FARMEASY_ANALYTICS_API_ACCESS_TOKEN enables constant-time validation of X-Analytics-Token. | Set a long random token before public deployment; send it only from server-side FarmEasy integration. |
| Rate limit | Default 120 requests/minute per direct client address. | Keep it enabled publicly and add a gateway/Redis limiter for multi-instance deployment. A value of 0 is only suitable for a trusted private network. |
| CORS | Disabled by default; FARMEASY_ANALYTICS_API_ALLOWED_ORIGINS is an explicit allow-list. | Prefer PHP-to-API server calls so browser code never receives the token. |
| Query safety | Every filter, date, page limit, and offset is a typed bound parameter. | Do not create endpoint-specific SQL by concatenating request values. |
| Error safety | 422, 429, 503, and 500 responses use one envelope. | Connection strings, exception traces, and Data.gov.in keys never appear in responses. |

Example grants, run by the database owner after views are deployed:

~~~sql
CREATE ROLE farmeasy_analytics_api LOGIN PASSWORD 'replace-with-a-secret';
GRANT CONNECT ON DATABASE farmeasy_analytics TO farmeasy_analytics_api;
GRANT USAGE ON SCHEMA analytics TO farmeasy_analytics_api;
GRANT SELECT ON
  analytics.vw_dashboard_volatility,
  analytics.vw_dashboard_market_freshness,
  analytics.vw_dashboard_latest_market_comparison,
  analytics.vw_dashboard_price_trends,
  analytics.vw_dashboard_data_quality
TO farmeasy_analytics_api;
~~~

Use the actual database name and an encrypted secret store in production. The
API does not require direct access to raw data, facts, or dimension tables.

## Response conventions

All list endpoints use bounded, zero-based pagination:

~~~json
{
  "data": [{ "example": "row" }],
  "pagination": { "limit": 50, "offset": 0, "total": 241 }
}
~~~

Every request error has this stable shape:

~~~json
{
  "error": {
    "code": "invalid_request",
    "message": "Request validation failed.",
    "details": [{ "field": "query.limit", "message": "Input should be greater than or equal to 1" }]
  }
}
~~~

Prices use the source price_unit, normally INR/quintal for the current
Data.gov.in price resource. The API does not silently convert to kilograms.
modal_price is a reported modal market price, not profit or a guaranteed farmer
realization.

## Endpoints

Common optional dimension filters are state, district, market, commodity,
variety, and grade. They are whitespace-normalized and case-insensitive against
the warehouse's standardized keys. Every collection accepts limit (1–500,
default 50) and offset (0+, default 0).

| Endpoint | Key parameters | Returns | Interpretation |
| --- | --- | --- | --- |
| GET /api/analytics/commodities | search | Known commodity/variety/grade series with coverage dates and reporting-mandi count. | Use before a commodity selector is populated. |
| GET /api/analytics/markets | Common location filters; search | Markets with most recent report date and stale flag. | Helps identify active or stale reporting mandis. |
| GET /api/analytics/prices/latest | Common filters; include_suspicious=false | Latest quote per mandi/commodity with min, max, modal, spread, regional benchmark, and rank. | Use for a current comparison; inspect quality status. |
| GET /api/analytics/prices/trends | Common filters; date_from and date_to in YYYY-MM-DD | Daily market series with 7/30-day moving averages and prior reporting-day modal price. | Use for observed 7/30/90-day movement, not forecasting. |
| GET /api/analytics/markets/compare | Required commodity; optional common filters; include_suspicious=false | Latest market ranking and regional differences plus an advisory. | A higher modal price is only one decision input. |
| GET /api/analytics/volatility | commodity; min_observation_count (default 2) | Commodity-level standard deviation, coefficient of variation, spread, and suspicious-row count. | Series with little history are excluded by default. |
| GET /api/analytics/data-quality | source_name; run_status (running, succeeded, failed) | Pipeline run totals, duplicate/rejection/suspicion counts, freshness, and logged issues. | Presents trust and freshness beside business metrics. |

The market-comparison endpoint deliberately requires a commodity. Ranking
unrelated commodities together would make a best-mandi result meaningless.

## Examples

Retrieve the latest non-suspicious Tomato quotes in Karnataka:

~~~powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/analytics/prices/latest?state=Karnataka&commodity=Tomato&limit=25" `
  -Headers @{ "X-Analytics-Token" = $env:FARMEASY_ANALYTICS_API_ACCESS_TOKEN }
~~~

Compare Tomato markets in one district:

~~~json
{
  "advisory": "A higher reported modal price is not guaranteed profit. Compare transport distance and cost, quality/grade, commissions, market fees, buyer demand, and available quantity before choosing a mandi.",
  "data": [
    {
      "market_date": "2026-09-08",
      "market_name": "Mysuru APMC",
      "commodity_name": "Tomato",
      "modal_price": "1400.00",
      "price_unit": "INR/quintal",
      "price_spread": "800.00",
      "difference_from_district_average": "25.00",
      "state_modal_price_rank": 1,
      "quality_status": "valid"
    }
  ],
  "pagination": { "limit": 50, "offset": 0, "total": 1 }
}
~~~

Price decimals may be encoded as strings so their source precision is not lost.
The client should render them as numeric values with the accompanying
price_unit.

## FarmEasy integration boundary

The PHP application should call this service from its server, not browser
JavaScript:

1. A farmer opens a FarmEasy insight page or a future marketplace comparison.
2. PHP validates its own user/session policy and calls the local/private
   analytics API with the token stored in server environment configuration.
3. FastAPI validates filters, reads PostgreSQL dashboard views, and returns a
   bounded JSON response.
4. PHP renders only the needed fields and the market-comparison advisory.

This keeps the existing marketplace intact and lets the analytics API evolve
independently. A short connection timeout, response-size limit, and graceful
fallback message should be used by any future PHP adapter.

For an interview: “I exposed only governed analytical read models through a
typed boundary. The marketplace does not need warehouse credentials, and price
comparison remains explicit about transport, quality, fees, and quantity.”

## Validation

API tests use a deterministic fake repository, so they do not call PostgreSQL
or any government endpoint. They cover all seven routes, pagination, parameter
validation, date-range validation, normalized filters, no credential leakage on
database failure, service-token enforcement, and rate limiting. Repository
tests additionally prove request values are passed as bound SQL parameters.
