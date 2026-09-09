# Official data sources and acquisition contract

## Primary price source

FarmEasy Mandi Price and Supply Intelligence uses the Government of India
resource **Current Daily Price of Various Commodities from Various Markets
(Mandi)** as its primary observed-price source.

| Item | Contract value |
| --- | --- |
| Publisher | Directorate of Marketing and Inspection (DMI), Department of Agriculture and Farmers Welfare, Ministry of Agriculture and Farmers Welfare |
| Upstream system | AGMARKNET |
| Resource ID | `9ef84268-d588-465a-a308-a864a43d0070` |
| Official catalog | [Current daily price of various commodities from various markets (Mandi)](https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi) |
| Official resource page | [Current Daily Price of Various Commodities from Various Markets (Mandi)](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi) |
| API base | `https://api.data.gov.in/resource` |
| Resource endpoint | `https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070` |
| Stated cadence | Daily; it is an administrative daily dataset, not a real-time trading feed. |

The official catalog says the resource contains wholesale minimum, maximum,
and modal prices reported by markets and that it is generated through
[AGMARKNET](https://agmarknet.gov.in/). Preserve both the source observation
date and the time FarmEasy retrieved it. A later API response does not make an
older `arrival_date` a live quote.

The pinned, machine-readable contract lives in
[`../config/data_gov_current_mandi.json`](../config/data_gov_current_mandi.json).
It is deliberately free of credentials and is the source of truth for source
identity, field mappings, fallback headers, and acquisition policy.

## API ingestion

The API key is required by Data.gov.in but must only be supplied at runtime in
`FARMEASY_ANALYTICS_DATA_GOV_API_KEY`. It must never appear in a committed URL,
raw-data filename, test fixture, log, notebook output, or dashboard. The
resource ID is public and is configured separately as
`FARMEASY_ANALYTICS_DATA_GOV_RESOURCE_ID`.

An illustrative request shape is below. `${FARMEASY_ANALYTICS_DATA_GOV_API_KEY}`
is a shell placeholder, not a key.

```text
GET https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
    ?api-key=${FARMEASY_ANALYTICS_DATA_GOV_API_KEY}
    &format=json
    &offset=0
    &limit=1000
```

Optional exact-match filters use the bracket syntax
`filters[field_id]=value` (for example, `filters[commodity]=Onion`). Field IDs
must be read from the response/schema contract before using a new filter; they
are source-owned spellings and an alias may legitimately return no rows.
Supported price-resource identifiers are currently `state`, `district`,
`market`, `commodity`, `variety`, and `grade`.

### Pagination and repeatability

The JSON response exposes a `records` array plus page metadata including
`count`, `limit`, `offset`, and the source-reported matching `total`. Fetch with
`offset=0`, preserve the raw page, and request successive offsets. When `total`
is present, stop when the returned rows reach it; otherwise use a short or empty
page as the terminal signal. Increment the next offset by the number of rows
actually returned, not by an assumed server maximum.

The API does not provide a stable observation identifier or a documented global
ordering guarantee. Data can change while a run is paginating, so a page
boundary can repeat or miss a record. The ingestion layer therefore:

1. records the retrieval timestamp, requested offset, returned count, response
   status, and source resource ID for every page;
2. retains raw payloads before transformation;
3. de-duplicates observations across pages and across runs using the canonical
   natural grain and a stable hash; and
4. upserts with a database unique constraint rather than assuming a one-time
   import is complete.

`count` and `total` are useful source diagnostics, not a durable historical
guarantee. Server-side limit caps or source changes are handled by the actual
array length and raw receipts. A non-success response, malformed JSON, or
response without a list-valued `records` field fails the page/run explicitly and
is not silently treated as an empty market.

## Source schema and CSV differences

The API JSON uses lower-case, underscore-separated field identifiers. The
official downloadable CSV has publisher-facing headings; price headings are
commonly XML-escaped. Do **not** map CSV by position. Read and validate its
header row, map only documented aliases, and write the original headers to the
pipeline-run log. Unknown or ambiguous headings are a validation error.

| Canonical field | API JSON field | Official CSV header / accepted official header variant | Required | Notes |
| --- | --- | --- | --- | --- |
| `state` | `state` | `State` | Yes | Reporting state or UT. |
| `district` | `district` | `District` | Yes | Reporting district. |
| `market` | `market` | `Market` | Yes | Mandi/market name. |
| `commodity` | `commodity` | `Commodity` | Yes | Commodity label supplied by the publisher. |
| `variety` | `variety` | `Variety` | No | Keep separate from commodity for fair comparisons. |
| `grade` | `grade` | `Grade` | No | Keep separate from variety. |
| `market_date` | `arrival_date` | `Arrival_Date` (also seen as `Arrival Date`) | Yes | An observation/reporting date; it is not an arrival volume. Source dates are expected day-first (`DD/MM/YYYY`); ISO dates are accepted only as an explicitly documented source variant. |
| `min_price` | `min_price` | `Min_x0020_Price` (decoded form: `Min Price`) | Yes | Preserve raw text, then parse as decimal. |
| `max_price` | `max_price` | `Max_x0020_Price` (decoded form: `Max Price`) | Yes | Preserve raw text, then parse as decimal. |
| `modal_price` | `modal_price` | `Modal_x0020_Price` (decoded form: `Modal Price`) | Yes | Modal means the most commonly reported/traded price, not an arithmetic average. |

The configured CSV aliases additionally accept lower-case API-like headings
when an official export uses them. That tolerance is intentionally narrow: it
does not authorize an undocumented third-party file to masquerade as an
official download.

Price values must be handled as `Decimal`, not binary floating point. The
resource does not carry an explicit row-level price-unit field. FarmEasy stores
the dataset-level convention as `INR/quintal` and must quarantine a source
variant that documents a conflicting unit rather than convert values by guess.
The UI should describe prices as *reported mandi prices* and show their source
date, not promise a farmer's realised sale price.

## Local CSV fallback

CSV is a resilience path, not a second data source. It is accepted only when a
user manually downloads it from the official resource/catalog above and passes
the file to the local ingest command. The manifest must record:

- the original filename and SHA-256 checksum;
- the official download URL, user/download timestamp, and file encoding;
- the exact header row and selected header mapping; and
- the number of raw, valid, duplicate, suspicious, and rejected rows.

The pipeline must neither upload that CSV to Git nor use an arbitrary internet
mirror. An absent, malformed, or stale CSV should fail with an actionable error
instead of causing historical data to be overwritten.

## AGMARKNET access policy

AGMARKNET is the provenance cited by the Data.gov.in catalog, but FarmEasy does
not scrape its HTML pages. In particular, the project will not solve, bypass,
or outsource CAPTCHAs; automate browsers against protected pages; reuse browser
cookies/session tokens; or build a fallback around a CAPTCHA-protected form.

The permitted automated path is the authenticated official Data.gov.in API.
The permitted manual fallback is a CSV downloaded from the official
Data.gov.in resource/catalog. If either path becomes unavailable, record a
failed pipeline run and surface freshness status; do not substitute a
third-party source without a reviewed source-contract change.

## Arrival and supply limitations

This price resource has `arrival_date`, but it has **no verified
`arrival_quantity` or `arrival_unit` field**. `arrival_date` is a date and must
never be counted or interpreted as supply. Consequently:

- `fact_market_arrivals` is not loaded from this source;
- arrival quantity, supply trends, and the Power BI Supply and Arrivals page
  remain disabled; and
- missing price observations mean missing reporting, not zero arrivals or zero
  trade.

Arrival analytics may be enabled only after a separate official government
source is documented with its source URL, licence, refresh cadence, quantity
definition, unit, conversion rules, field-level validation, and grain. It must
remain a separate fact table so inferred supply never contaminates observed
price facts.

## Attribution, licence, and user-facing caution

The catalog is released under the National Data Sharing and Accessibility
Policy, and Data.gov.in publishes content under the
[Government Open Data License - India](https://data.gov.in/godl). That licence
allows lawful reuse and derivative work but requires attribution, prohibits
implied endorsement, and disclaims warranties/continuous availability.

Use this attribution in project documentation and dashboard footers, updating
the access date at release time:

> Directorate of Marketing and Inspection (DMI), Department of Agriculture and
> Farmers Welfare, Ministry of Agriculture and Farmers Welfare, Government of
> India. *Current Daily Price of Various Commodities from Various Markets
> (Mandi)*, Open Government Data Platform India, accessed YYYY-MM-DD,
> https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi.
> Published under Government Open Data License - India:
> https://data.gov.in/godl.

FarmEasy does not imply government endorsement. “Best mandi” is an observed
price comparison only; a farmer's economic choice also depends on distance,
transport, fees, quality/grade acceptance, buyer liquidity, and available
quantity. The source's daily reporting gaps and possible corrections must be
visible through the data-quality and freshness indicators.
