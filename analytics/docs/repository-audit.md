# Existing FarmEasy repository audit

Audit date: 2026-09-08. This records the baseline before the analytics module.

## Current stack and structure

FarmEasy is a server-rendered, procedural PHP application using `mysqli` and a
MySQL/MariaDB schema in [`farmeasy.sql`](../../farmeasy.sql). It uses Bootstrap
3, jQuery, static CSS, image assets, and PHP sessions. There is no dependency
manager, framework, ORM, migration tool, JSON API, automated test suite, or
existing Python code.

| Area | Evidence | Assessment |
| --- | --- | --- |
| Connection | [`db.php`](../../db.php) | Shared MySQL connection; reads environment variables with local defaults. |
| Authentication | [`Login/login.php`](../../Login/login.php), [`Login/signUp.php`](../../Login/signUp.php) | Session-based farmer and buyer sign-in/sign-up. |
| Products | [`uploadProduct.php`](../../uploadProduct.php), [`productMenu.php`](../../productMenu.php) | Farmers create marketplace listings; buyers filter them by category. |
| Buying | [`buyNow.php`](../../buyNow.php), [`favorites.php`](../../favorites.php) | Buyer transaction/contact capture and favourites. |
| Reviews | [`review.php`](../../review.php), [`reviewInput.php`](../../reviewInput.php) | Listing review workflow. |
| UI | [`index.php`](../../index.php), [`menu.php`](../../menu.php), `css/`, `bootstrap/`, `js/` | Server-rendered pages with shared navigation and static assets. |

## Existing database and models

The SQL dump defines six operational tables:

| Table | Purpose | Analytics relationship |
| --- | --- | --- |
| `farmer` | Farmer account/profile | Do not join to official mandi observations. |
| `buyer` | Buyer account/profile | Out of scope for the price warehouse. |
| `fproduct` | Product listing, category, description, listing price | Its `price` is a seller-set ₹/kg retail price, not a mandi quotation. |
| `favorites` | Buyer/product relationship | Operational only. |
| `review` | Product review/rating | Operational only. |
| `transaction` | Buyer contact/purchase request | Operational only. |

Primary keys exist for `buyer`, `farmer`, `fproduct`, and `transaction`.
There are no location, mandi, commodity-master, historical price, arrival, or
analytical-quality tables. The operational dump uses `latin1`, while the
analytics warehouse will use PostgreSQL UTF-8 to preserve government names.

## Reuse and integration boundary

Reusable pieces are the FarmEasy product/commodity vocabulary, shared navigation,
session-aware access patterns, and environment-based connection convention. The
analytics module stays under top-level `analytics/`, uses its own PostgreSQL
connection, and exposes curated read models later.

When the PHP UI is extended, it should call a read-only analytics HTTP endpoint
or a narrow server-side adapter. It must not issue ETL work during a page
request and must never expose an analytics database URL or API key to a browser.

## Risks and conflicts avoided

1. The PHP code uses interpolated SQL queries. The analytics feature will use
   parameterized queries and will not refactor unrelated transactional paths.
2. MySQL operational tables and PostgreSQL analytical tables have different
   responsibilities. A separate database/schema prevents reporting workloads
   from degrading checkout, listing, and session flows.
3. The legacy application is compatible with older PHP conventions. A separate
   Python service avoids imposing modern Python dependencies on PHP deployment.
4. Official price data does not identify a FarmEasy seller or guarantee profit.
   Insights will distinguish observed mandi prices from private listing prices
   and warn about freight, quality, fees, and available quantities.
5. The current daily price API has no verified arrivals quantity/unit. Arrival
   analytics stays optional until a field-level government source is configured.
6. PHP is not installed in this workspace, so legacy PHP linting cannot be run;
   all new Python code receives an independent test/lint workflow.
