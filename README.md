# FarmEasy Mandi Price and Supply Intelligence

FarmEasy Mandi Price and Supply Intelligence is a portfolio-quality analytics
extension for the existing FarmEasy local-farming marketplace. It preserves the
original PHP/MySQL product while adding a repeatable Python/PostgreSQL pipeline
for official Indian mandi-price intelligence.

It helps farmers, buyers, and marketplace operators compare observed mandi
prices, inspect time-series movement and price risk, understand data freshness,
and make a more informed selling decision. It does not present a higher quoted
price as guaranteed profit.

> This repository contains the application source extracted from the original
> project archive. The archive itself is intentionally not committed so GitHub
> can track and review the source files normally.

## Existing FarmEasy marketplace

- PHP with `mysqli`
- MySQL / MariaDB
- Bootstrap 3, jQuery, HTML, and CSS

The original source has procedural PHP pages and a MySQL operational schema for
buyers, farmers, products, favourites, reviews, and transactions. A seller
listing price is distinct from an official mandi quote and is never mixed into
the analytics fact table. See
[the repository audit](analytics/docs/repository-audit.md) for the complete
assessment and compatibility risks.

## Legacy marketplace setup (Windows)

1. Install a local PHP + MySQL stack such as XAMPP.
2. Create a database named `farmeasy`.
3. Import [`farmeasy.sql`](farmeasy.sql) with phpMyAdmin or MySQL.
4. Configure `FARMEASY_DB_*` environment variables in your web-server setup
   (or use the supplied local-development defaults in `db.php`).
5. Configure your web server to serve this directory, then open `index.php`.

The connection file reads `FARMEASY_DB_HOST`, `FARMEASY_DB_PORT`,
`FARMEASY_DB_NAME`, `FARMEASY_DB_USER`, and `FARMEASY_DB_PASSWORD`. It retains
the original local-development defaults when those values are not supplied.
The later Python analytics module reads `.env` directly; PHP itself receives
environment variables from its web-server configuration.

## Repository hygiene

- `.env` is ignored; use `.env.example` as the safe template.
- The source archive and local database backups are ignored.
- The included SQL file defines the marketplace schema; it contains no seeded
  account or transaction data.

## Analytics system

The analytics module is intentionally separate from the marketplace:

- official Data.gov.in API ingestion with environment-held credentials;
- local CSV fallback for repeatable offline loading;
- immutable raw receipts, manifests, and SHA-256 lineage;
- validation, standardization, and data-quality quarantine;
- idempotent PostgreSQL star-schema loading;
- documented business SQL and dashboard-ready views;
- a reproducible EDA notebook, Power BI measures/theme/build guide;
- a read-only FastAPI contract for future FarmEasy pages; and
- deterministic tests that do not use live government services.

## Business problem and users

Farmers often see price information that is fragmented, stale, or difficult to
compare across mandis. Buyers and FarmEasy operators similarly need context
about market variation rather than a single isolated number.

| User | Decision supported |
| --- | --- |
| Farmer | Compare recent modal prices, freshness, spread, and regional benchmarks before deciding where to sell. |
| Agricultural buyer | Understand local versus nearby market conditions and whether quotes are volatile. |
| FarmEasy operator | Monitor source quality, stale reporting markets, and coverage before displaying insights. |
| Analyst or interviewer | Trace a KPI from raw source through validation, warehouse, SQL, dashboard, and API. |

## Questions the system answers

- Which mandi has the highest latest modal price for a selected commodity?
- How do min, max, and modal price differ by mandi, district, and state?
- How has the observed price moved over 7, 30, and 90 days?
- Which commodity series have the highest standard deviation or coefficient of
  variation?
- Which records are suspicious, missing, duplicate, stale, or conflicting?
- How frequently does each mandi report, and how fresh is its latest quote?
- What does price spread reveal about market range and uncertainty?

Arrival or supply analysis is deliberately disabled until a verified government
source supplies both arrival quantity and unit. The current price source's
arrival_date is a reporting date, not volume.

## Architecture

~~~mermaid
flowchart LR
    S[Data.gov.in API or official CSV] --> E[Extract and raw receipt layer]
    E --> V[Validate and standardize]
    V --> T[Transform and quality report]
    T --> W[(PostgreSQL analytics star schema)]
    W --> Q[Business SQL and dashboard views]
    Q --> BI[Power BI]
    Q --> API[Read-only FastAPI]
    API --> PHP[Future FarmEasy PHP server-side adapter]
~~~

The PHP marketplace continues to use MySQL/MariaDB. The analytics warehouse is
a separate PostgreSQL database with its own roles and never writes to FarmEasy
operational tables.

## Technology decisions

| Component | Selection | Why it fits |
| --- | --- | --- |
| Pipeline | Python 3, Pandas | Clear, testable tabular cleaning and transformation. |
| Warehouse | PostgreSQL star schema | Strong window functions, analytical indexes, Power BI support, and governed views. |
| Database access | SQLAlchemy with psycopg | Safe parameter binding with explicit, reviewable SQL. |
| Source client | HTTPX | Timeouts, retries, pagination, and mockable failures. |
| Analysis | Jupyter Notebook and SQL | Reproducible EDA plus production-style business queries. |
| Dashboard | Power BI artifacts | Source-controlled DAX, theme, model instructions, and views; no pretend pbix file. |
| Application boundary | FastAPI | Typed filters, pagination, consistent errors, OpenAPI docs, and a least-privilege read model. |
| Testing | Pytest and Ruff | Deterministic validation, loader, SQL asset, notebook, and API checks. |

Each decision, alternative, and interview explanation is summarized in
[the technical decision log](analytics/docs/decisions.md).

## Official data sources

1. Data.gov.in current daily price of various commodities in various markets:
   resource ID 9ef84268-d588-465a-a308-a864a43d0070.
2. AGMARKNET is recognized as the market-price authority behind the source
   ecosystem; the project does not scrape CAPTCHA-protected pages.
3. An official local CSV exported or obtained through an approved government
   channel can use the same pipeline as a fallback.

The source mapping and limitations are documented in
[data sources](analytics/docs/data-sources.md). API keys are read only from
environment variables and are never committed.

## Project structure

~~~text
FarmEasy/
├── index.php, db.php, farmeasy.sql        Legacy marketplace
├── analytics/
│   ├── config/                            Source and name-alias configuration
│   ├── data/raw, processed, quality_reports  Git-ignored runtime artifacts
│   ├── notebooks/                         Reproducible EDA notebook
│   ├── powerbi/                           DAX measures and theme
│   ├── sql/schema/                        Warehouse DDL
│   ├── sql/analysis/                      17 documented business queries
│   ├── sql/views/                         Dashboard/API read models
│   ├── src/farmeasy_mandi_analytics/
│   │   ├── extract, validate, transform, quality, load, storage
│   │   └── api/                           Read-only FastAPI boundary
│   ├── tests/                             Deterministic fixtures and tests
│   └── docs/                              Architecture, API, BI, dictionary
├── .env.example                           Safe configuration template
└── .gitignore                             Protects secrets and runtime data
~~~

## Windows setup

### Prerequisites

- Python 3.11 or later
- PostgreSQL 15 or later for warehouse/API work
- Power BI Desktop for dashboard construction
- XAMPP or another PHP/MySQL stack only if running the legacy marketplace

### Create the Python environment

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\analytics[dev,api,notebook]"
Copy-Item .env.example .env
~~~

Populate .env without committing it. Important settings are:

| Setting | Purpose |
| --- | --- |
| FARMEASY_ANALYTICS_DATABASE_URL | Dedicated PostgreSQL analytics database; never the legacy MySQL URL. |
| FARMEASY_ANALYTICS_DATA_GOV_API_KEY | Data.gov.in key for API extraction only. |
| FARMEASY_ANALYTICS_DATA_GOV_RESOURCE_ID | Current daily mandi-price resource ID. |
| FARMEASY_ANALYTICS_PAGE_SIZE and LOOKBACK_DAYS | Bounded source ingestion behaviour. |
| FARMEASY_ANALYTICS_STALE_AFTER_DAYS | Freshness threshold for market warnings. |
| FARMEASY_ANALYTICS_SUSPICIOUS_CHANGE_PCT | Price-change threshold for review flags. |
| FARMEASY_ANALYTICS_API_ACCESS_TOKEN | Server-side token required for a public API deployment. |
| FARMEASY_ANALYTICS_API_RATE_LIMIT_PER_MINUTE | Single-process API guard; keep enabled publicly. |

The complete safe template is [.env.example](.env.example).

## Run the pipeline

First review data without a database:

~~~powershell
.\.venv\Scripts\farmeasy-mandi.exe validate-csv .\downloads\official-mandi-prices.csv --run-id csv-20260909 --reference-date 2026-09-09
~~~

This writes a raw receipt, processed validated data, and a data-quality report
under Git-ignored analytics data folders.

Load the same CSV into PostgreSQL:

~~~powershell
.\.venv\Scripts\farmeasy-mandi.exe load-csv .\downloads\official-mandi-prices.csv --run-id csv-20260909 --reference-date 2026-09-09
.\.venv\Scripts\farmeasy-mandi.exe deploy-views
~~~

Use the official API when a Data.gov.in key is configured:

~~~powershell
.\.venv\Scripts\farmeasy-mandi.exe validate-api --state Karnataka --reference-date 2026-09-09
.\.venv\Scripts\farmeasy-mandi.exe load-api --state Karnataka --reference-date 2026-09-09
~~~

Repeated loads do not create duplicate facts. Source observation hash is unique,
and PostgreSQL upserts change a fact only when its source content or quality
state changes.

## Data quality and warehouse

Hard-invalid records are quarantined with reasons; suspicious rows remain
visible and are flagged. The quality report includes raw/valid/rejected counts,
duplicates, conflicts, missing values, suspicious prices, reporting gaps,
stale markets, freshness, and timestamp.

Read [the data-quality policy](analytics/docs/data-quality.md) and
[the data dictionary](analytics/docs/data-dictionary.md) for exact rules. The
star schema, keys, indexes, and Mermaid ER diagram are in
[the warehouse schema guide](analytics/docs/warehouse-schema.md).

## SQL analysis

The project includes 17 documented business queries. They cover joins,
aggregates, CTEs, ranking, LAG, LEAD, rolling averages, conditional
aggregation, quality monitoring, and an index-aware EXPLAIN review.

See [the SQL analysis guide](analytics/docs/sql-query-guide.md) and
[the query file](analytics/sql/analysis/01_business_queries.sql). Each query
starts with its business question, why it matters, and expected interpretation.

## EDA notebook

Open analytics/notebooks/mandi_price_eda.ipynb after a validated run, or set
FARMEASY_EDA_DATA_PATH to a processed CSV. It covers:

- dataset overview and column definitions;
- missing values, duplicates, and descriptive statistics;
- price distributions, commodity/market/state/district comparison;
- time series, volatility, and outlier investigation;
- quality conclusions; and
- dynamically generated findings and actionable recommendations.

Every chart has a title, labelled axes, unit-aware labels, and a short
interpretation. The repository verifies it against a tiny test-only synthetic
fixture; no official raw data is stored in Git.

## Power BI dashboard

The repository provides views, DAX measures, a theme, relationships, and
step-by-step Windows build instructions rather than claiming to produce a
binary pbix in this environment.

Dashboard pages:

1. Executive Overview
2. Commodity Price Explorer
3. Best Mandi Comparison
4. Volatility and Risk
5. Data Quality
6. Supply and Arrivals, conditional on a verified arrival source

Follow [the Power BI build guide](analytics/docs/powerbi-build-guide.md), use
[the DAX measures](analytics/powerbi/farmeasy_mandi_measures.dax), and import
[the theme](analytics/powerbi/farmeasy_mandi_theme.json).

## FarmEasy analytics API

After views are deployed, start the read-only service:

~~~powershell
.\.venv\Scripts\uvicorn.exe farmeasy_mandi_analytics.api.app:create_production_app --factory --host 127.0.0.1 --port 8000
~~~

Available routes include commodities, markets, latest prices, trends, market
comparison, volatility, and data quality. Every collection validates filters,
uses bounded pagination, and returns a consistent error object. The market
comparison route always includes the reminder that price alone does not account
for distance, transport cost, quality, commissions, fees, buyer demand, or
available quantity.

Read [the API guide](analytics/docs/api.md) and
[the FarmEasy integration design](analytics/docs/farmeasy-integration.md)
before connecting a PHP screen. Keep token-bearing calls server-to-server.

## Findings and recommendations

No data-dependent claim is hardcoded in this repository. Run the pipeline
against an official extract first; the notebook then generates at least five
findings and three recommendations from the selected data.

The decision framework is:

- prefer a recent, valid quote over a higher but stale or suspicious price;
- compare modal price against district/state average and price spread together;
- treat high coefficient of variation as risk, not a selling recommendation;
- investigate reporting gaps before describing a market as inactive; and
- include transport, grade/quality, fees, demand, and available quantity before
  choosing a selling mandi.

## Limitations and version two

- Current price intelligence has no verified arrival quantity or unit, so it
  does not fabricate supply analytics.
- A production instance still needs a PostgreSQL service, API key, TLS/reverse
  proxy, secrets management, and optional gateway rate limiting.
- Power BI Desktop is needed to create a locally rendered pbix from the
  supplied reproducible assets.
- This version is descriptive and diagnostic only. Forecasting is a clearly
  separate future version after sufficient clean historical data, leakage
  controls, baseline evaluation, and a distinction between observed and
  predicted values.

## Testing and release verification

~~~powershell
.\.venv\Scripts\python.exe -m ruff format --check analytics\src analytics\tests
.\.venv\Scripts\python.exe -m ruff check analytics\src analytics\tests
.\.venv\Scripts\python.exe -m pytest analytics\tests
git diff --check
~~~

Read [the release verification record](analytics/docs/verification.md) for
what is automated and what requires an external service.

## Screenshots

Add screenshots after building the Power BI report or a FarmEasy insight page.
Do not commit screenshots containing credentials, farmer personal data, or
unverified source records.

## Resume-ready description

Built FarmEasy Mandi Price and Supply Intelligence: a production-style Python,
Pandas, PostgreSQL, SQL, Power BI, and FastAPI analytics system for official
Indian mandi-price data. Designed idempotent raw-to-warehouse ingestion,
auditable data-quality controls, star-schema KPI views, 17 business SQL
queries, dashboard-ready DAX assets, and a secure read-only integration API
while preserving the legacy PHP/MySQL marketplace.
