# Phased execution plan

This plan preserves the PHP marketplace while the analytical system becomes
independently testable and deployable.

## Phase 1 — foundation and data contract

**Deliverables:** package layout; configuration; canonical fields; data-quality
contracts; project audit; architecture and data-contract docs; starter tests.

**Files:** `analytics/pyproject.toml`, `analytics/src/farmeasy_mandi_analytics/`,
`analytics/data/`, `analytics/docs/`, root `.env.example`, root `.gitignore`.

**Decision:** use a Python `src/` package and environment-based settings rather
than embedding scripts in PHP pages. This keeps repeatability, tests, and
credential isolation clear. Interview explanation: “I separated operational
commerce from analytical workloads and made configuration portable.”

**Validation:** configuration tests pass; secret values are redacted; tracked
files contain no `.env` or raw production data.

**Risks/assumptions:** no PostgreSQL server or Data.gov.in key is required at
scaffold time; both are runtime configuration, not repository content.

## Phase 2 — official-source ingestion and raw receipts

**Deliverables:** Data.gov.in paginated client, CSV fallback, request retries,
raw JSON/CSV receipt storage, manifest and SHA-256 fingerprinting.

**Files:** `src/extract/`, source mappings in `config/`, CLI commands, fixtures,
and extraction tests.

**Decision:** preserve immutable raw receipts before transformation. Interview
explanation: “It makes a government-data pipeline replayable and auditable.”

**Validation:** mocked page traversal, retryable failure, malformed response,
and CSV ingestion tests; a repeated receipt produces the same fingerprint.

**Risk:** resource identifiers and source fields may evolve, so they remain
configuration-driven and source mapping is documented.

## Phase 3 — validation, standardization, and transformation

**Deliverables:** field mapping, strict date/number parsing, text
canonicalization, duplicate detection, price-rule validation, volatility flags,
missing-date and staleness checks, and a quality summary.

**Files:** `src/validate/`, `src/transform/`, `src/quality/`, fixtures/tests,
and quality-report templates.

**Decision:** invalid and suspicious records are logged rather than silently
dropped. Interview explanation: “Quality outcomes are first-class analytical
data.”

**Validation:** deterministic fixtures cover every required quality rule.

## Phase 4 — PostgreSQL analytical warehouse

**Deliverables:** `analytics` schema, star-schema tables, indexes, DDL/deploy
scripts, idempotent loader, run log, and data-quality persistence.

**Files:** `sql/schema/`, `src/load/`, `src/pipeline.py`, loader tests and
optional PostgreSQL integration tests.

**Decision:** surrogate keys support stable dimensions while a source-row hash
is the idempotency key. Interview explanation: “Natural source fields can
change; hash-based uniqueness stops page and re-run duplicates.”

**Validation:** schema parses; loader uses `ON CONFLICT`; repeated fixture loads
do not increase fact count; PostgreSQL tests run when a test URL is configured.

**Status:** complete in code. The deterministic loader test proves no-op repeat
behavior with a recording database boundary. An optional real-PostgreSQL test
is skipped unless `FARMEASY_TEST_DATABASE_URL` points to a dedicated disposable
database; this workspace has no local PostgreSQL service installed.

## Phase 5 — business SQL and dashboard-ready views

**Deliverables:** at least 15 documented business queries; CTE, window, ranking,
`LAG`/`LEAD`, rolling-average, and quality queries; views/materialized-view
refresh guidance.

**Files:** `sql/analysis/`, `sql/views/`, `docs/sql-query-guide.md`.

**Decision:** put reusable KPI logic in database views rather than duplicating
it across Power BI and the API. Interview explanation: “One governed semantic
layer prevents KPI drift.”

**Validation:** SQL lint/parse checks and execution against test data when a
PostgreSQL service is available.

## Phase 6 — EDA and Power BI assets

**Deliverables:** reproducible notebook, dashboard specification, relationships,
DAX measures, theme, and Windows import instructions.

**Files:** `notebooks/`, `powerbi/`, and supporting docs.

**Decision:** provide source-controlled dashboard artifacts instead of claiming
an unversionable `.pbix` was generated. Interview explanation: “The model and
DAX are reviewable and reproducible.”

**Validation:** notebook executes after a processed dataset is supplied; DAX
references dashboard views and defined fields.

**Status:** complete. The notebook executes against a deterministic,
test-only validated fixture, static Power BI assets are JSON-validated, and
the notebook/Python/dashboard checks pass. A .pbix is intentionally not
claimed because Power BI Desktop is not available in this workspace.

## Phase 7 — FarmEasy-ready analytics API

**Deliverables:** FastAPI routes, validated filters, pagination, consistent
errors, read-only repository/service layers, API documentation, and tests.

**Files:** `src/api/`, `tests/test_api*.py`, `docs/api.md`, and
`docs/farmeasy-integration.md`.

**Decision:** deploy a small service beside the PHP app rather than mixing ETL
and session routes. Interview explanation: “The UI receives a stable,
least-privilege service contract.”

**Validation:** route tests use a fake repository; no test calls a live
government API; database-level pagination is parameterized.

**Status:** complete in code. Seven read-only endpoints use typed filters,
bounded pagination, a consistent error envelope, optional service-token
enforcement, and a per-process rate guard. Tests use a fake repository and
therefore need neither a live API key nor PostgreSQL.

## Phase 8 — portfolio documentation and release verification

**Deliverables:** full README, data dictionary, architecture/ER diagrams,
limitations, findings/recommendations workflow, reproducible Windows guide, and
verification report.

**Files:** root README and `analytics/docs/`.

**Validation:** full unit suite, linting, Git status review, and an explicit
record of unavailable runtime checks such as a missing PostgreSQL service.

**Status:** complete in code and documentation. Final verification recorded
83 passed tests, one intentionally skipped optional PostgreSQL integration
test, and no lint, formatting, JSON, or Git-whitespace failures. External
deployment checks remain explicitly documented in `docs/verification.md`.
