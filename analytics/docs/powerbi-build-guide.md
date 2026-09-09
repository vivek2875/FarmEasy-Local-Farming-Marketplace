# Power BI build guide

This project provides a reproducible Power BI model rather than pretending to
ship a generated `.pbix` file. Deploy the database views first:

```powershell
\.venv\Scripts\farmeasy-mandi.exe deploy-views
```

The command requires `FARMEASY_ANALYTICS_DATABASE_URL` and a PostgreSQL account
with permission to create views in the `analytics` schema.

## 1. Import model (Windows)

1. Open Power BI Desktop and choose **Get data → PostgreSQL database**.
2. Enter the server and database from the PostgreSQL connection string. Choose
   **Import** for the portfolio model; use DirectQuery only after validating
   database capacity and gateway behaviour.
3. In the Navigator, select and rename these objects exactly as shown:

| PostgreSQL object | Power BI name | Role |
| --- | --- | --- |
| `analytics.dim_date` | `Dim Date` | Calendar/date slicer |
| `analytics.dim_location` | `Dim Location` | State and district attributes |
| `analytics.dim_market` | `Dim Market` | Mandi attributes |
| `analytics.dim_commodity` | `Dim Commodity` | Commodity, variety, grade attributes |
| `analytics.vw_mandi_price_observations` | `Mandi Price Observations` | Main analytical fact/read model |
| `analytics.vw_dashboard_price_trends` | `Price Trends` | 7/30-day trend read model |
| `analytics.vw_dashboard_latest_market_comparison` | `Latest Market Comparison` | Best-mandi comparison read model |
| `analytics.vw_dashboard_volatility` | `Volatility` | Commodity risk read model |
| `analytics.vw_dashboard_market_freshness` | `Market Freshness` | Stale-market read model |
| `analytics.vw_dashboard_reporting_coverage` | `Reporting Coverage` | Reporting-gap rate read model |
| `analytics.vw_dashboard_data_quality` | `Data Quality` | Pipeline-run quality summary |
| `analytics.data_quality_log` | `Data Quality Issues` | Detailed quality issue table |

4. In Power Query, ensure price fields are **Decimal number**, percentage
   fields are **Decimal number** (then format as percent/one decimal place),
   date fields are **Date**, and timestamps are **Date/Time/Time Zone** as
   appropriate. Keep `source_observation_hash` as text.
5. Mark `Dim Date[full_date]` as the date table. The loader fills its calendar
   range so Power BI time-intelligence functions see non-reporting dates.
6. In Model view, create the relationships below. Use a single filter direction
   from dimensions toward facts/read models to avoid ambiguous paths.

## 2. Relationships

| From (1) | To (*) | Active | Filter direction |
| --- | --- | --- | --- |
| `Dim Location[location_key]` | `Dim Market[location_key]` | Yes | Single |
| `Dim Date[date_key]` | `Mandi Price Observations[date_key]` | Yes | Single |
| `Dim Date[date_key]` | `Price Trends[date_key]` | Yes | Single |
| `Dim Market[market_key]` | `Mandi Price Observations[market_key]` | Yes | Single |
| `Dim Market[market_key]` | `Price Trends[market_key]` | Yes | Single |
| `Dim Market[market_key]` | `Latest Market Comparison[market_key]` | Yes | Single |
| `Dim Market[market_key]` | `Market Freshness[market_key]` | Yes | Single |
| `Dim Market[market_key]` | `Reporting Coverage[market_key]` | Yes | Single |
| `Dim Commodity[commodity_key]` | `Mandi Price Observations[commodity_key]` | Yes | Single |
| `Dim Commodity[commodity_key]` | `Price Trends[commodity_key]` | Yes | Single |
| `Dim Commodity[commodity_key]` | `Latest Market Comparison[commodity_key]` | Yes | Single |
| `Dim Commodity[commodity_key]` | `Volatility[commodity_key]` | Yes | Single |
| `Dim Commodity[commodity_key]` | `Reporting Coverage[commodity_key]` | Yes | Single |
| `Data Quality[run_id]` | `Data Quality Issues[run_id]` | Yes | Single |

Do not relate `Data Quality` to prices. Pipeline quality is a separate
operational lineage; mixing it into the price fact creates bidirectional filter
ambiguity. Keep `Volatility` disconnected from dates because it is an aggregate
over its full loaded history.

## 3. DAX measures

Create the measures in
[`../powerbi/farmeasy_mandi_measures.dax`](../powerbi/farmeasy_mandi_measures.dax).
The table names above are intentional: changing them requires updating DAX.

Core KPIs include latest/average/median modal price, 7/30-day averages,
week-over-week and month-over-month change, standard deviation/CV, active
mandis, data freshness, best mandi, reporting gaps, and pipeline quality.
Format price measures using the source unit (normally `INR/quintal`) and do not
call them “per kg” unless an explicitly documented conversion is added.

## 4. Dashboard pages and visuals

### Executive Overview

| KPI or question | Recommended visual | Data/measure |
| --- | --- | --- |
| Latest average modal price | Card | `Latest Average Modal Price` |
| Week-over-week change | KPI/card with directional colour | `Week-over-Week Change %` |
| Active mandis | Card | `Active Reporting Mandis` |
| Commodities covered | Card | `Commodities Covered` |
| Data freshness | Card | `Data Freshness Days` + `Latest Report Date` |
| Highest volatility commodity | Card | `Highest Volatility Commodity`, `Highest Volatility CV %` |
| Price trend | Line chart | `Dim Date[full_date]`, `Average Modal Price`, 7/30-day measures |
| State comparison | Sorted bar chart | `Dim Location[state_name]`, `Latest Average Modal Price` |

Add commodity, state, and date slicers in a persistent top filter bar.

### Commodity Price Explorer

Use slicers for commodity, variety, grade, state, district, mandi, and date
range. Add cards for min, max, median, modal, 7-day, and 30-day values. Use a
line chart from `Price Trends` for daily/7-day/30-day values; pair it with a
clustered bar chart that compares selected mandis. Use a tooltip page showing
price spread and quality status for the hovered market/date.

### Best Mandi Comparison

Use `Latest Market Comparison` in a matrix sorted by `state_modal_price_rank`
then modal price. Show mandi, latest date, modal price, district/state
benchmark differences, price-spread percentage, quality status, and freshness.
Add this fixed warning as a textbox:

> Higher modal price is not guaranteed profit. Compare distance, transport,
> handling, market fees, grade/quality, buyer demand, and sale quantity first.

### Volatility and Risk

Use a ranked bar chart of `Volatility[modal_price_coefficient_of_variation_pct]`,
a table of largest increases/decreases from `Price Trends`, a scatter chart of
price spread versus modal price, and a table of suspicious observations. Add
`Market Freshness` and `Reporting Coverage` cards/charts so price volatility is
not interpreted without reporting quality.

### Data Quality

Use cards for raw rows, valid rows, rejected rows, duplicates, missing-field
issues, stale markets, and last successful run. Add a stacked column chart of
`Data Quality Issues[issue_code]` by severity, a matrix of pipeline runs, and a
stale-market table from `Market Freshness`. This page should make clear that
quality warnings are not hidden from price users.

### Supply and Arrivals — conditional only

Create this page only after a verified official source provides arrival quantity
and unit, the optional arrivals schema is deployed, and arrival tests pass.
Then use arrival quantity (normalized kg), 30-day arrival trend, commodity,
market, and unit-consistency measures. Do not show zero values merely because
the default price source lacks arrivals.

## 5. Filter, drill-through, and interaction behaviour

- Sync the commodity, state, district, market, and date slicers across the
  first four pages.
- Configure a **Mandi Detail** drill-through target with market, commodity,
  variety, and grade keys. Include history, spread, volatility, and quality
  evidence there.
- Configure a **Commodity Detail** drill-through target with commodity key;
  show state ranking, time trend, and reporting coverage.
- Keep Data Quality run/date filters local to the Data Quality page, so a
  pipeline-run selection cannot make the price facts look absent.
- Disable chart cross-filtering where it makes a benchmark misleading; use
  report-page tooltips to explain filters and source unit.

## 6. Theme and accessibility

Import `farmeasy_mandi_theme.json` through **View → Themes → Browse for
themes**. The palette uses forest green for primary positive insight, saffron
for attention, blue for comparison, and red only for error/suspicion. Never use
colour alone: add a data label, icon, or status text for warning/error states.

## 7. Refresh and security

- Store PostgreSQL credentials in Power BI's data-source settings or an
  enterprise gateway, never in a `.pbix` note or source-controlled file.
- Schedule a pipeline run before dataset refresh. A dashboard refresh cannot
  make stale raw data current.
- Use a read-only database account for Power BI, limited to the `analytics`
  schema/views needed for reporting.
- For production publishing, configure a gateway and document ownership of the
  source API key separately from Power BI credentials.

For an interview: “The BI model uses governed warehouse views for reusable
calculations, a star-shaped relationship model for filtering, and an explicit
quality page so visual polish never hides source limitations.”
