# Technical decision log

| Decision | Why this fits | Alternative considered | Interview explanation |
| --- | --- | --- | --- |
| Separate Python package | Legacy PHP has no data-pipeline runtime and must remain stable. | Adding scripts to PHP pages. | “I isolated batch analytics from operational web traffic.” |
| PostgreSQL star schema | Strong support for window functions, materialized views, BI tools, and dimensional querying. | Reusing FarmEasy MySQL. | “The warehouse is optimized for reporting, not checkout.” |
| Pandas transformations | Well-suited for tabular cleaning, missing-value profiling, and deterministic fixtures. | Manual row loops. | “Vectorized transformations are clearer and testable at dataset scale.” |
| SQLAlchemy + psycopg | Gives safe connections and testable database boundaries without an overbuilt framework. | Raw string-only database calls. | “I retain explicit SQL while keeping connection handling portable.” |
| HTTPX client | Supports timeouts, pagination, retry policy, and mocked HTTP tests. | Browser scraping. | “I consume the official API contract, not unstable HTML.” |
| FastAPI only at the boundary | Lightweight validation and OpenAPI documentation for curated read endpoints. | Exposing PostgreSQL or embedding ETL in PHP. | “The UI receives a stable, least-privilege service contract.” |
| Dashboard views as API read models | Makes the API and Power BI use the same governed KPI logic. | Recalculating metrics separately in PHP. | “One semantic layer reduces KPI drift.” |
| Optional token plus local rate guard | Supports private local development while making public deployment explicitly protected. | A public database proxy or browser-held secret. | “I keep credentials server-side and enforce bounded access.” |
