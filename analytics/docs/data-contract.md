# Canonical mandi-price data contract

The source schema is mapped into the following canonical columns before any
warehouse load. `market_date` is the date of the published market observation;
the Data.gov.in source labels its equivalent field `arrival_date`.

| Canonical field | Required | Type after transformation | Definition |
| --- | --- | --- | --- |
| `market_date` | Yes | date | Reporting/arrival date of the official quotation. |
| `state` | Yes | string | Canonical Indian state/UT name. |
| `district` | Yes | string | Canonical district name. |
| `market` | Yes | string | Mandi/market name. |
| `commodity` | Yes | string | Commodity name. |
| `variety` | No | string | Reported variety; `Unknown` when not supplied. |
| `grade` | No | string | Reported grade; `Unknown` when not supplied. |
| `min_price` | Yes | decimal | Minimum quoted price in the source price unit. |
| `max_price` | Yes | decimal | Maximum quoted price in the source price unit. |
| `modal_price` | Yes | decimal | Most frequently occurring/reported price, not an average. |
| `price_unit` | No | string | Assumed/inferred only when the source contract documents it. |
| `arrival_quantity` | No | decimal | Supply quantity; never manufactured when absent. |
| `arrival_unit` | No | string | Unit paired with a verified arrival quantity. |
| `source_name` | Yes | string | Official publisher/data-source identifier. |
| `source_record_id` | No | string | Source-provided row identifier, when present. |

The transformed dataset additionally contains the original source values prefixed
with `raw_`, normalized matching keys, source hashes, derived price-spread
metrics, and a `quality_status`. Those fields make a cleaned row traceable
without overwriting the receipt that supplied it.

## Core price rules

1. `min_price`, `max_price`, and `modal_price` must parse as positive numbers.
2. `min_price <= max_price`.
3. `modal_price` must be within the inclusive minimum–maximum range.
4. Required text fields cannot be blank after normalization.
5. A stable **observation hash** covers source, date, location, market,
   commodity, variety, and grade. A separate **content hash** adds price and
   verified-arrival values. This distinguishes an exact duplicate from a
   conflicting correction at the same observation grain.
6. Exact duplicates are quarantined after the first occurrence in a run;
   conflicting rows are also quarantined and logged for review.
7. A large change from the preceding market/commodity observation is a warning,
   not an automatic rejection.

## Quality status

`valid` means the row passed hard validation with no warnings. `warning` means
the price is usable but has a non-price-quality warning (such as a stale market
or mixed verified arrival units). `suspicious` means it is usable but its modal
price movement crossed the configured review threshold. Neither warning status
is silently removed from the analytical output.

## Arrival-data policy

The current daily price API does not include an arrival quantity or unit.
Arrival facts, KPIs, and the Power BI supply page are only enabled after a
documented official source exposes both a quantity and a compatible unit.
Missing arrival values are not interpreted as zero supply.
