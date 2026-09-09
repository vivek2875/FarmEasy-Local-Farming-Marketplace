# SQL business-analysis guide

Run the core schema and dashboard views before executing
[`../sql/analysis/01_business_queries.sql`](../sql/analysis/01_business_queries.sql).
The file contains 17 parameterized PostgreSQL questions; every statement starts
with its business question, why it matters, and interpretation guidance.

| Query | Focus | SQL concepts demonstrated |
| --- | --- | --- |
| 01 | Best fresh mandi shortlist | CTE, ranking, decision safeguard |
| 02 | State/district comparison | joins, aggregates, median |
| 03 | 7/30/90-day trend | dashboard view, calendar-day moving averages |
| 04–05 | Commodity and mandi volatility | `STDDEV_SAMP`, coefficient of variation, `FILTER` |
| 06 | Suspicious prices | CTE, latest successful run, quality join |
| 07 | Stale markets | freshness view |
| 08 | Min/max/modal spread | aggregate and conditional aggregation |
| 09 | Week-over-week movement | `LAG`, CTEs |
| 10 | Month-over-month movement | `LAG`, date grouping |
| 11 | Missing reporting rate | `GENERATE_SERIES`, CTEs, coverage calculation |
| 12 | Pipeline health | data-quality view, conditional rate |
| 13 | Active mandi coverage | CTE and conditional aggregation |
| 14 | Better-price candidates | ranked latest-market view, regional benchmark |
| 15 | Trend-deviation screen | rolling-average view, outlier investigation |
| 16 | Next-report trajectory | `LEAD` window functions |
| 17 | Index-aware access review | `EXPLAIN (ANALYZE, BUFFERS)` |

The `:parameter_name` syntax is suitable for a parameterized application query
layer. In `psql`, replace it with a literal only for trusted local exploration;
never build production SQL by concatenating a URL parameter or form input.

For an interview: “I wrote each query to answer a business decision, not to
show syntax. The reusable views govern KPI definitions, and the analysis file
uses the same model the dashboard and API will use.”
