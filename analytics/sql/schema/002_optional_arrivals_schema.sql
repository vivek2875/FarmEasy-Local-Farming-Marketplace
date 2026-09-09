-- OPTIONAL: apply only after a structured, official source has been verified to
-- provide both arrival quantity and a documented arrival unit. The current
-- Data.gov.in daily price resource does not meet that condition, so this file
-- is not run by the default pipeline.

CREATE TABLE IF NOT EXISTS analytics.fact_market_arrivals (
    market_arrival_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name VARCHAR(128) NOT NULL,
    source_observation_hash CHAR(64) NOT NULL,
    source_content_hash CHAR(64) NOT NULL,
    date_key INTEGER NOT NULL REFERENCES analytics.dim_date(date_key) ON DELETE RESTRICT,
    market_key BIGINT NOT NULL REFERENCES analytics.dim_market(market_key) ON DELETE RESTRICT,
    commodity_key BIGINT NOT NULL REFERENCES analytics.dim_commodity(commodity_key)
        ON DELETE RESTRICT,
    arrival_quantity NUMERIC(16, 3) NOT NULL CHECK (arrival_quantity > 0),
    arrival_unit VARCHAR(32) NOT NULL CHECK (BTRIM(arrival_unit) <> ''),
    arrival_quantity_kg NUMERIC(18, 3) NOT NULL CHECK (arrival_quantity_kg > 0),
    first_loaded_run_id VARCHAR(128) NOT NULL REFERENCES analytics.pipeline_run_log(run_id)
        ON DELETE RESTRICT,
    last_loaded_run_id VARCHAR(128) NOT NULL REFERENCES analytics.pipeline_run_log(run_id)
        ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fact_market_arrivals_source_observation UNIQUE (
        source_name,
        source_observation_hash
    )
);

CREATE INDEX IF NOT EXISTS idx_fact_market_arrivals_commodity_date
    ON analytics.fact_market_arrivals (commodity_key, date_key DESC);
CREATE INDEX IF NOT EXISTS idx_fact_market_arrivals_market_date
    ON analytics.fact_market_arrivals (market_key, date_key DESC);
