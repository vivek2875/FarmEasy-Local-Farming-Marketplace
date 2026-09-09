# Dashboard-view deployment

Run `001_dashboard_views.sql` only after the core warehouse schema exists:

```powershell
psql --set ON_ERROR_STOP=1 --dbname "<PostgreSQL connection string>" `
  --file .\analytics\sql\views\001_dashboard_views.sql
```

The views deliberately retain `quality_status` and warning counts so Power BI
and the integration API can distinguish observed data from unreviewed data.
They do not create arrival metrics because the current primary source supplies
no verified arrival quantity/unit.

`vw_dashboard_price_trends` uses calendar-day window frames for its 7-day and
30-day moving averages. A sparse source period therefore averages available
reports; it does not invent zero-price or zero-arrival days. Dashboard filters
can further restrict the state, district, market, commodity, variety, grade,
or source.
