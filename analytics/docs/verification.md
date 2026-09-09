# Release verification record

This document records what the repository can prove in the current workspace
and what needs an external runtime before it can be verified.

## Automated checks

Run from the repository root:

~~~powershell
.\.venv\Scripts\python.exe -m ruff format --check analytics\src analytics\tests
.\.venv\Scripts\python.exe -m ruff check analytics\src analytics\tests
.\.venv\Scripts\python.exe -m pytest analytics\tests
.\.venv\Scripts\python.exe -m json.tool analytics\notebooks\mandi_price_eda.ipynb
.\.venv\Scripts\python.exe -m json.tool analytics\powerbi\farmeasy_mandi_theme.json
git diff --check
~~~

## Result recorded on 2026-09-09

- Ruff format check: passed, 47 files already formatted.
- Ruff lint check: passed.
- Pytest: 83 passed, 1 skipped, 0 failed.
- JSON validation: passed for the EDA notebook and Power BI theme.
- Git whitespace check: passed.

The skipped test is the intentional PostgreSQL integration test because
FARMEASY_TEST_DATABASE_URL is not configured in this workspace. The suite
emitted three dependency/runtime warnings: two from FastAPI/Starlette test
client deprecations and one Windows ZeroMQ event-loop warning while executing
the notebook. None came from project code and no test failed.

The suite is deliberately deterministic: it uses mocked Data.gov.in pages,
synthetic CSV fixtures, fake API repositories, and a test-only EDA fixture. It
never contacts a live government endpoint.

## Runtime checks intentionally outside this workspace

| Check | Why it is not marked passed here | How to verify before deployment |
| --- | --- | --- |
| Live Data.gov.in API ingestion | No user API key is stored in the repository. | Put the key in a local .env, run validate-api for a narrow state/date scope, and inspect the quality report. |
| PostgreSQL loader and view execution | No PostgreSQL service or disposable test database is configured locally. | Set FARMEASY_TEST_DATABASE_URL to a dedicated disposable database, run the optional integration test, then run load-csv and deploy-views. |
| Power BI report rendering | Power BI Desktop and a .pbix cannot be generated in this environment. | Follow the Power BI build guide against the views and import the supplied DAX/theme assets. |
| Legacy PHP lint/smoke test | PHP/XAMPP is not installed in this workspace. | Import farmeasy.sql in a local XAMPP MySQL instance and use PHP lint plus the marketplace smoke-test checklist. |
| Public API perimeter | Public TLS, gateway limits, and a secrets manager are deployment controls. | Put FastAPI behind HTTPS/reverse proxy, set the service token, retain a gateway rate limiter, and test only from the PHP server. |

No raw official dataset, API key, database password, or generated Power BI file
is committed to Git.
