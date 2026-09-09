# Warehouse schema deployment

`001_analytics_schema.sql` is the required PostgreSQL schema for price
intelligence. It is intentionally separate from `farmeasy.sql`, the legacy
MySQL/MariaDB marketplace schema.

The Python loader applies the core schema before loading. A database operator
may also run it manually:

```powershell
psql --set ON_ERROR_STOP=1 --dbname "<PostgreSQL connection string>" `
  --file .\analytics\sql\schema\001_analytics_schema.sql
```

Do **not** apply `002_optional_arrivals_schema.sql` until an official source has
been documented to provide both arrival quantity and unit. The current default
Data.gov.in price resource does not expose those fields.

## Why the model is dimensional

`fact_mandi_prices` holds one source observation at the date × market ×
commodity/variety/grade grain. `dim_date`, `dim_location`, `dim_market`, and
`dim_commodity` reduce repeated labels and make analytical joins predictable.
`pipeline_run_log` and `data_quality_log` retain operational lineage alongside
the facts without mixing it into the FarmEasy commerce database.

The source observation hash is unique for each official observation grain;
re-running the same data cannot add a second fact. A later source correction
updates that fact only when its content hash changes, while the immutable raw
receipt and quality log retain the evidence.
