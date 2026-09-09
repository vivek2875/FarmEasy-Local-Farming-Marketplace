# FarmEasy integration design

FarmEasy remains a PHP/MySQL marketplace. Mandi intelligence is a separate
Python/PostgreSQL analytical workload. The connection between them is a
read-only HTTP boundary, not shared database tables.

~~~mermaid
flowchart LR
    G[Data.gov.in / approved CSV] --> P[Python extract, validate, transform]
    P --> W[(PostgreSQL analytics schema)]
    W --> V[Governed dashboard views]
    V --> A[FastAPI analytics service]
    A --> B[FarmEasy PHP server-side adapter]
    B --> U[Farmer or buyer screen]
    V --> BI[Power BI]
~~~

## Why this boundary is appropriate

| Choice | Why | Alternative not selected | Interview explanation |
| --- | --- | --- | --- |
| Separate FastAPI service | It validates requests and has generated API documentation while leaving procedural PHP stable. | Adding ETL logic to PHP pages. | “Operational commerce and analytical reads have different workloads and privileges.” |
| Server-to-server call | The analytics token and database URL stay off the browser. | Calling the analytics API directly from JavaScript. | “Secrets remain in backend configuration, not client code.” |
| Dashboard views only | API and Power BI share governed KPI definitions. | Rewriting every KPI in PHP. | “One semantic layer prevents drift between screens and reports.” |
| Optional token plus local rate guard | Local development stays simple; public deployment has an explicit protection path. | An unauthenticated public database proxy. | “I keep credentials server-side and enforce bounded access.” |

## Safe rollout sequence

1. Create a separate PostgreSQL analytics database and configure the pipeline
   writer URL in .env.
2. Run load-csv or load-api, inspect the generated quality report, and deploy
   the views.
3. Create the read-only API role shown in the API documentation.
4. Set FARMEASY_ANALYTICS_API_ACCESS_TOKEN and start FastAPI on a private
   address or behind a TLS reverse proxy.
5. Add the same token and an internal base URL such as http://127.0.0.1:8000
   only to the FarmEasy server environment.
6. Add a small PHP adapter only to pages where an insight is useful; retain the
   existing marketplace view if the service times out or has no recent data.
7. Monitor the data-quality endpoint and the pipeline run log before
   presenting a current-price claim.

Do not reuse FARMEASY_DB_PASSWORD, the Data.gov.in API key, or the pipeline
writer credentials for the API adapter.

## Suggested first user experience

Use GET /api/analytics/markets/compare?commodity=Tomato&district=Mysuru on a
future seller insight page. Present:

- reporting date and price unit;
- min, modal, and max quote;
- the selected mandi's difference from the district average;
- freshness and quality status; and
- the decision warning about transport, quality, commissions, fees, buyer
  demand, and available quantity.

Do not overwrite a seller's fproduct.price, call it an official quote, or
claim the comparison predicts profit. The listing price remains a marketplace
seller input; the mandi quote is external observed market intelligence.

## PHP adapter contract

Keep any future adapter narrow and reusable. It should:

- obtain FARMEASY_ANALYTICS_API_BASE_URL and the token from the server
  environment;
- allow only listed API paths, with a five-second connect/read timeout;
- URL-encode parameters and send Accept: application/json;
- send X-Analytics-Token only to the approved internal host;
- treat non-200, malformed JSON, and an empty data list as a safe insight
  temporarily unavailable state;
- cache successful, dated results briefly if the product requirement needs it;
  never cache a raw token in HTML or browser storage.

This repository intentionally does not alter a legacy PHP page yet. It first
delivers and tests the standalone contract so a UI addition can be reviewed as
a small, reversible change rather than coupling it to ETL work.
