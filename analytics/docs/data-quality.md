# Data-quality policy and local reports

FarmEasy keeps three layers of evidence for every run:

1. **Raw receipt:** byte-for-byte API page or local CSV stored with a SHA-256
   fingerprint and a redacted manifest.
2. **Validated dataset:** usable, standardized price observations saved in
   `analytics/data/processed/<run-id>/`.
3. **Quality evidence:** JSON summary plus rejected and suspicious-record CSVs
   saved in `analytics/data/quality_reports/<run-id>/`.

The runtime data folders are deliberately Git-ignored. They can contain large
official downloads, but their structure is reproducible from the source and
configuration.

## Error rules — row is quarantined

| Rule | Reason recorded |
| --- | --- |
| Required field absent | `missing_required_value` |
| Date cannot parse as `DD/MM/YYYY` or ISO `YYYY-MM-DD` | `invalid_date` |
| Price cannot parse as a finite decimal | `non_numeric_price` |
| Minimum, maximum, or modal price is zero/negative | `non_positive_price` |
| Minimum exceeds maximum | `invalid_price_range` |
| Modal price is outside its inclusive min/max range | `modal_price_outside_range` |
| Same observation grain and content appears more than once | `duplicate_observation` |
| Same observation grain has inconsistent price/content | `conflicting_observation` |

The first valid occurrence of an exact duplicate is retained. A conflicting row
is not selected automatically; it remains in the report for human review.

## Warning rules — price row remains usable

| Rule | Meaning |
| --- | --- |
| `suspicious_price_change` | Modal price changed beyond `FARMEASY_ANALYTICS_SUSPICIOUS_CHANGE_PCT` from the previous observation for the same location, market, commodity, variety, and grade. |
| `missing_reporting_date` | A date is absent between first and last observed dates for the same market/commodity grain. It means a reporting gap, never zero supply. |
| `stale_market` | Latest record for a market is older than `FARMEASY_ANALYTICS_STALE_AFTER_DAYS` relative to the run reference date. |
| `invalid_arrival_quantity` / `invalid_arrival_unit` | Optional arrival data cannot be used; price intelligence continues. |
| `mixed_arrival_units` | Verified arrival rows use more than one unit; normalized kilograms are the only safe aggregation basis. |

Name cleanup collapses whitespace and normalizes casing. Only aliases explicitly
listed in `analytics/config/name_aliases.json` change a name's meaning. For
example, `Orissa` maps to `Odisha`; the source value remains available as a
`raw_` field. This prevents an over-aggressive fuzzy match from joining two
different mandis.

## Running a deterministic local validation

```powershell
\.venv\Scripts\farmeasy-mandi.exe validate-csv `
  .\downloads\official-mandi-prices.csv `
  --run-id local-20260908 `
  --reference-date 2026-09-08 `
  --official-source-url "https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi"
```

`--reference-date` is optional for ordinary runs; without it, the pipeline uses
the current UTC date. Passing it makes freshness and reporting-gap tests fully
reproducible. The command does not load PostgreSQL yet: it preserves raw input,
creates the processed CSV, and creates the quality artifacts.

## Quality summary fields

`data_quality_report.json` contains `raw_rows_received`, `valid_rows_loaded`,
`invalid_rows_rejected`, `duplicates_removed`,
`conflicting_observation_count`, `suspicious_price_count`,
`missing_value_counts`, `missing_reporting_date_count`, `stale_market_count`,
`data_freshness_date`, and `pipeline_executed_at`, plus every issue and its
source row number. Metadata is redacted before it is written so API keys and
password-like values cannot enter the report.

For an interview: “I made quality outcomes part of the data model. Analysts can
reproduce a row from the raw receipt, quantify trust in a dashboard, and review
exceptions instead of losing them during cleaning.”
