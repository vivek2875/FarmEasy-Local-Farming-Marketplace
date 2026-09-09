# FarmEasy Mandi Price and Supply Intelligence

This module is the analytical complement to the legacy FarmEasy PHP/MySQL
marketplace. It ingests official Indian mandi-price data, preserves raw source
receipts, validates and standardizes records, loads an analytical PostgreSQL
warehouse, and supplies SQL, Power BI, and API-ready outputs.

The module deliberately does **not** write to the operational FarmEasy MySQL
tables. A farmer's listing price in `fproduct` is a marketplace price, not an
official mandi quotation; mixing them would make both analyses misleading.

## Development setup

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".\analytics[dev,api,notebook]"
Copy-Item .env.example .env
```

Populate FARMEASY_ANALYTICS_DATABASE_URL for PostgreSQL loading and the
read-only service. Set FARMEASY_ANALYTICS_DATA_GOV_API_KEY and
FARMEASY_ANALYTICS_DATA_GOV_RESOURCE_ID only when extracting from the official
source API. Set FARMEASY_ANALYTICS_API_ACCESS_TOKEN before exposing the
service beyond a trusted private network. The data source and setup guide are
documented in docs/.

## Current build status

Phases 1–7 are complete in code: configuration and contracts; official
API/CSV raw ingestion; validation and quality evidence; idempotent PostgreSQL
loading; governed SQL; EDA/Power BI assets; and a read-only FastAPI boundary.
Phase 8 is the portfolio documentation and release-verification pass.

Useful local commands after installation:

```powershell
# Safe configuration check: secrets are redacted.
\.venv\Scripts\farmeasy-mandi.exe show-config

# Preserve an official CSV and create validated + quality outputs.
\.venv\Scripts\farmeasy-mandi.exe validate-csv .\downloads\mandi-prices.csv `
  --run-id local-20260908 --reference-date 2026-09-08

# Run the same flow into the dedicated PostgreSQL warehouse.
\.venv\Scripts\farmeasy-mandi.exe load-csv .\downloads\mandi-prices.csv `
  --run-id local-20260908 --reference-date 2026-09-08

# The official API offers the same offline and PostgreSQL flows.
\.venv\Scripts\farmeasy-mandi.exe validate-api --state Karnataka
\.venv\Scripts\farmeasy-mandi.exe load-api --state Karnataka

# Run the deterministic suite; it never calls a live government API.
\.venv\Scripts\python.exe -m pytest analytics\tests

# Start the read-only analytics API after PostgreSQL views are deployed.
\.venv\Scripts\uvicorn.exe farmeasy_mandi_analytics.api.app:create_production_app `
  --factory --host 127.0.0.1 --port 8000
```

Read [the phased plan](docs/implementation-plan.md),
[official-source notes](docs/data-sources.md), and
[data-quality policy](docs/data-quality.md) before using a live source. See
[the warehouse schema](docs/warehouse-schema.md) before configuring PostgreSQL.
For service deployment and endpoint contracts, read
[the API guide](docs/api.md) and
[FarmEasy integration design](docs/farmeasy-integration.md).
