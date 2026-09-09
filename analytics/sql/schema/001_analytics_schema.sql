-- FarmEasy Mandi Price and Supply Intelligence: core PostgreSQL warehouse.
-- Apply this file to a dedicated PostgreSQL database, never the legacy
-- FarmEasy MySQL/MariaDB operational database.

CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE IF NOT EXISTS analytics.pipeline_run_log (
    run_id VARCHAR(128) PRIMARY KEY,
    source_name VARCHAR(128) NOT NULL,
    raw_manifest_path TEXT,
    status VARCHAR(16) NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    raw_rows_received INTEGER NOT NULL DEFAULT 0 CHECK (raw_rows_received >= 0),
    valid_rows_loaded INTEGER NOT NULL DEFAULT 0 CHECK (valid_rows_loaded >= 0),
    invalid_rows_rejected INTEGER NOT NULL DEFAULT 0 CHECK (invalid_rows_rejected >= 0),
    duplicates_removed INTEGER NOT NULL DEFAULT 0 CHECK (duplicates_removed >= 0),
    conflicting_observation_count INTEGER NOT NULL DEFAULT 0
        CHECK (conflicting_observation_count >= 0),
    suspicious_price_count INTEGER NOT NULL DEFAULT 0 CHECK (suspicious_price_count >= 0),
    missing_reporting_date_count INTEGER NOT NULL DEFAULT 0
        CHECK (missing_reporting_date_count >= 0),
    stale_market_count INTEGER NOT NULL DEFAULT 0 CHECK (stale_market_count >= 0),
    data_freshness_date DATE,
    fact_rows_affected INTEGER NOT NULL DEFAULT 0 CHECK (fact_rows_affected >= 0),
    quality_issues_logged INTEGER NOT NULL DEFAULT 0 CHECK (quality_issues_logged >= 0),
    configuration_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_summary TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS analytics.dim_date (
    date_key INTEGER PRIMARY KEY CHECK (date_key BETWEEN 19000101 AND 29991231),
    full_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    calendar_quarter SMALLINT NOT NULL CHECK (calendar_quarter BETWEEN 1 AND 4),
    calendar_month SMALLINT NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
    month_name VARCHAR(16) NOT NULL,
    iso_week SMALLINT NOT NULL CHECK (iso_week BETWEEN 1 AND 53),
    day_of_month SMALLINT NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
    day_of_week SMALLINT NOT NULL CHECK (day_of_week BETWEEN 1 AND 7),
    day_name VARCHAR(16) NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics.dim_location (
    location_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state_name VARCHAR(128) NOT NULL CHECK (BTRIM(state_name) <> ''),
    state_normalized VARCHAR(128) NOT NULL CHECK (BTRIM(state_normalized) <> ''),
    district_name VARCHAR(128) NOT NULL CHECK (BTRIM(district_name) <> ''),
    district_normalized VARCHAR(128) NOT NULL CHECK (BTRIM(district_normalized) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_location_normalized UNIQUE (state_normalized, district_normalized)
);

CREATE TABLE IF NOT EXISTS analytics.dim_market (
    market_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    location_key BIGINT NOT NULL REFERENCES analytics.dim_location(location_key)
        ON DELETE RESTRICT,
    market_name VARCHAR(160) NOT NULL CHECK (BTRIM(market_name) <> ''),
    market_normalized VARCHAR(160) NOT NULL CHECK (BTRIM(market_normalized) <> ''),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_market_normalized UNIQUE (location_key, market_normalized)
);

CREATE TABLE IF NOT EXISTS analytics.dim_commodity (
    commodity_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    commodity_name VARCHAR(160) NOT NULL CHECK (BTRIM(commodity_name) <> ''),
    commodity_normalized VARCHAR(160) NOT NULL CHECK (BTRIM(commodity_normalized) <> ''),
    variety_name VARCHAR(160) NOT NULL CHECK (BTRIM(variety_name) <> ''),
    variety_normalized VARCHAR(160) NOT NULL CHECK (BTRIM(variety_normalized) <> ''),
    grade_name VARCHAR(80) NOT NULL CHECK (BTRIM(grade_name) <> ''),
    grade_normalized VARCHAR(80) NOT NULL CHECK (BTRIM(grade_normalized) <> ''),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_dim_commodity_normalized UNIQUE (
        commodity_normalized,
        variety_normalized,
        grade_normalized
    )
);

CREATE TABLE IF NOT EXISTS analytics.fact_mandi_prices (
    mandi_price_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name VARCHAR(128) NOT NULL,
    source_record_id VARCHAR(128),
    source_observation_hash CHAR(64) NOT NULL,
    source_content_hash CHAR(64) NOT NULL,
    date_key INTEGER NOT NULL REFERENCES analytics.dim_date(date_key) ON DELETE RESTRICT,
    market_key BIGINT NOT NULL REFERENCES analytics.dim_market(market_key) ON DELETE RESTRICT,
    commodity_key BIGINT NOT NULL REFERENCES analytics.dim_commodity(commodity_key)
        ON DELETE RESTRICT,
    min_price NUMERIC(14, 2) NOT NULL CHECK (min_price > 0),
    max_price NUMERIC(14, 2) NOT NULL,
    modal_price NUMERIC(14, 2) NOT NULL,
    price_unit VARCHAR(32) NOT NULL CHECK (BTRIM(price_unit) <> ''),
    price_spread NUMERIC(14, 2) NOT NULL CHECK (price_spread >= 0),
    price_spread_pct NUMERIC(14, 4) NOT NULL CHECK (price_spread_pct >= 0),
    quality_status VARCHAR(16) NOT NULL CHECK (quality_status IN ('valid', 'warning', 'suspicious')),
    quality_warning_codes TEXT NOT NULL DEFAULT '',
    first_loaded_run_id VARCHAR(128) NOT NULL REFERENCES analytics.pipeline_run_log(run_id)
        ON DELETE RESTRICT,
    last_loaded_run_id VARCHAR(128) NOT NULL REFERENCES analytics.pipeline_run_log(run_id)
        ON DELETE RESTRICT,
    first_loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_fact_mandi_prices_range CHECK (max_price >= min_price),
    CONSTRAINT ck_fact_mandi_prices_modal_range CHECK (
        modal_price >= min_price AND modal_price <= max_price
    ),
    CONSTRAINT uq_fact_mandi_prices_source_observation UNIQUE (source_name, source_observation_hash)
);

CREATE TABLE IF NOT EXISTS analytics.data_quality_log (
    quality_log_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL REFERENCES analytics.pipeline_run_log(run_id) ON DELETE RESTRICT,
    source_name VARCHAR(128) NOT NULL,
    issue_hash CHAR(64) NOT NULL,
    issue_code VARCHAR(64) NOT NULL,
    severity VARCHAR(16) NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
    reason TEXT NOT NULL,
    source_row_number INTEGER,
    source_observation_hash CHAR(64),
    field_name VARCHAR(128),
    record_context JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_data_quality_log_run_issue UNIQUE (run_id, issue_hash)
);

-- These support the most common date/market/commodity filters used by SQL,
-- Power BI, and the later read-only integration API.
CREATE INDEX IF NOT EXISTS idx_pipeline_run_log_status_started
    ON analytics.pipeline_run_log (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_dim_market_location
    ON analytics.dim_market (location_key);
CREATE INDEX IF NOT EXISTS idx_fact_mandi_prices_commodity_date
    ON analytics.fact_mandi_prices (commodity_key, date_key DESC);
CREATE INDEX IF NOT EXISTS idx_fact_mandi_prices_market_date
    ON analytics.fact_mandi_prices (market_key, date_key DESC);
CREATE INDEX IF NOT EXISTS idx_fact_mandi_prices_date_market
    ON analytics.fact_mandi_prices (date_key DESC, market_key);
CREATE INDEX IF NOT EXISTS idx_fact_mandi_prices_review_status
    ON analytics.fact_mandi_prices (quality_status, date_key DESC)
    WHERE quality_status <> 'valid';
CREATE INDEX IF NOT EXISTS idx_data_quality_log_run
    ON analytics.data_quality_log (run_id, severity, issue_code);
CREATE INDEX IF NOT EXISTS idx_data_quality_log_observation
    ON analytics.data_quality_log (source_observation_hash)
    WHERE source_observation_hash IS NOT NULL;
