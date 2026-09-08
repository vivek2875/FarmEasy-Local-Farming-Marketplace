# FarmEasy — Local Farming Marketplace

FarmEasy marketplace that lets farmers list agricultural
products and buyers browse products, save favourites, review listings, and
purchase directly from local producers.

> This repository contains the application source extracted from the original
> project archive. The archive itself is intentionally not committed so GitHub
> can track and review the source files normally.

## Technology

- MySQL / MariaDB
- Bootstrap 3, jQuery, HTML, and CSS

## Local setup (Windows)

1. Create a database named `farmeasy`.
2. Import [`farmeasy.sql`](farmeasy.sql) with phpMyAdmin or MySQL.
3. Copy `.env.example` to `.env` and set your local database credentials.
4. Configure your web server to serve this directory, then open `index.php`.

The connection file reads `FARMEASY_DB_HOST`, `FARMEASY_DB_PORT`,
`FARMEASY_DB_NAME`, `FARMEASY_DB_USER`, and `FARMEASY_DB_PASSWORD`. It retains
the original local-development defaults when those values are not supplied.

## Repository hygiene

- `.env` is ignored; use `.env.example` as the safe template.
- The source archive and local database backups are ignored.
- The included SQL file defines the marketplace schema; it contains no seeded
  account or transaction data.

## Planned extension

The project will gain a separate `analytics/` module for FarmEasy Mandi Price
and Supply Intelligence. It will keep the legacy PHP marketplace independent
from the repeatable Python/PostgreSQL analytics pipeline, then expose curated
insights through a narrow integration layer.
