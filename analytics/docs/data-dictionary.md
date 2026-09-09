# Data dictionary

## Grain and source meaning

The core fact grain is one validated official quotation for a reporting date,
market, commodity, variety, and grade. The current Data.gov.in source maps its
arrival_date field to market_date because that field is the published
quotation/reporting date; it is not an arrival-volume measure.

Price values remain in their supplied source unit, normally INR/quintal. The
pipeline never relabels them as per-kilogram values without an explicit,
documented conversion.

## Raw and canonical price fields

| Source/canonical field | Type | Meaning | Validation or transformation |
| --- | --- | --- | --- |
| source_name | text | Registered source identity, for example data_gov_current_mandi. | Required; part of fact idempotency key. |
| source_record_id | text | Source-side record identifier when provided. | Preserved for traceability; not assumed globally unique. |
| raw_arrival_date | text | Original source date text. | Preserved unchanged in processed output. |
| market_date | date | Official price quotation/reporting date. | Accepts DD/MM/YYYY or ISO date; invalid dates are quarantined. |
| raw_state, raw_district, raw_market | text | Original source location labels. | Preserved before standardization. |
| state, district, market | text | Canonical display labels. | Unicode/spacing/case cleanup plus only explicitly configured aliases. |
| state_normalized, district_normalized, market_normalized | text | Casefolded matching keys. | Used in dimension uniqueness and bound API filters. |
| raw_commodity, raw_variety, raw_grade | text | Original commodity classification. | Preserved before standardization. |
| commodity, variety, grade | text | Canonical commodity classification. | Variety and grade become Unknown only in the warehouse dimension when source values are absent. |
| min_price | decimal | Lowest reported price in the market range. | Must be positive and no greater than max_price. |
| max_price | decimal | Highest reported price in the market range. | Must be positive and no less than min_price. |
| modal_price | decimal | Most frequently reported market price. | Must be positive and lie inside the min/max range. |
| price_unit | text | Unit supplied or configured for the source. | Default current source setting: INR/quintal. |
| price_spread | decimal | max_price minus min_price. | Derived after price validation. |
| price_spread_pct | decimal | price_spread divided by modal_price times 100. | Derived; guards against zero modal price. |
| quality_status | text | valid, warning, or suspicious. | Suspicious rows remain visible for review. |
| quality_warning_codes | text | Comma-separated non-fatal issue codes. | Supports API and dashboard trust indicators. |
| source_observation_hash | SHA-256 text | Stable grain fingerprint. | Prevents duplicate re-loads across pages/runs. |
| source_content_hash | SHA-256 text | Full canonical content fingerprint. | Detects correction of a known source observation. |

## Warehouse tables

| Object | Primary key or grain | Business purpose |
| --- | --- | --- |
| analytics.dim_date | date_key; one calendar date | Time intelligence and explicit non-reporting dates. |
| analytics.dim_location | location_key; normalized state + district | Standardized location hierarchy. |
| analytics.dim_market | market_key; location + normalized market | Mandi identity; supports a repeated market name in different districts. |
| analytics.dim_commodity | commodity_key; normalized commodity + variety + grade | Product grain for quote comparison. |
| analytics.fact_mandi_prices | mandi_price_key; source_name + source_observation_hash unique | Validated price facts and their quality state. |
| analytics.pipeline_run_log | run_id | Run counts, freshness, timing, status, safe config snapshot, and lineage path. |
| analytics.data_quality_log | quality_log_key; run_id + issue_hash unique | Quarantined, suspicious, duplicate, stale, and reporting-gap evidence. |

The optional analytics.fact_market_arrivals table is not part of the deployed
core model. It must remain absent until a verified official source supplies
arrival quantity and unit.

## Pipeline and quality fields

| Field | Meaning |
| --- | --- |
| raw_rows_received | Source rows/pages received before validation. |
| valid_rows_loaded | Valid and warning/suspicious price rows eligible for warehouse loading. |
| invalid_rows_rejected | Rows quarantined for hard validation errors. |
| duplicates_removed | Exact duplicate observations detected within a run. |
| conflicting_observation_count | Same observation grain with materially inconsistent content. |
| suspicious_price_count | Valid rows flagged by the configured price-change threshold. |
| missing_reporting_date_count | Gaps between first and last observed reporting dates; never inferred supply. |
| stale_market_count | Markets older than the configured freshness threshold relative to the run. |
| data_freshness_date | Latest valid market_date available for the run. |
| fact_rows_affected | New or updated facts written by an idempotent load. |
| quality_issues_logged | Persisted error/warning/info events for the run. |

## Dashboard/read-model fields

| View | Important fields | Use |
| --- | --- | --- |
| vw_mandi_price_observations | quote dimensions, min/max/modal price, spread, quality status | Detail tables and granular measures. |
| vw_dashboard_price_trends | average daily prices, 7/30-day moving average, prior reporting-day price | Commodity and mandi time-series charts. |
| vw_dashboard_latest_market_comparison | latest market price, district/state average difference, state rank | Best-mandi comparison with decision caveat. |
| vw_dashboard_volatility | standard deviation, coefficient of variation, reporting-mandi count | Risk prioritization. |
| vw_dashboard_market_freshness | latest market date, days since report, stale flag | Freshness monitoring. |
| vw_dashboard_reporting_coverage | expected/actual/missing reporting days and rate | Reporting-gap analysis. |
| vw_dashboard_data_quality | run counts and issue totals | Data-quality dashboard and API. |

For an interview: “The dictionary makes field meaning and grain explicit. In
particular, I separated a reporting date from arrival volume so the analysis
cannot accidentally claim supply data that the source did not provide.”
