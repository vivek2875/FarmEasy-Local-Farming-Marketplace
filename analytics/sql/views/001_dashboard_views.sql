-- Dashboard-ready semantic views for the FarmEasy mandi-price warehouse.
-- Apply after sql/schema/001_analytics_schema.sql.

CREATE OR REPLACE VIEW analytics.vw_mandi_price_observations AS
SELECT
    f.mandi_price_key,
    f.source_name,
    f.source_record_id,
    f.source_observation_hash,
    f.source_content_hash,
    d.date_key,
    d.full_date AS market_date,
    d.calendar_year,
    d.calendar_quarter,
    d.calendar_month,
    d.month_name,
    d.iso_week,
    l.location_key,
    l.state_name,
    l.state_normalized,
    l.district_name,
    l.district_normalized,
    m.market_key,
    m.market_name,
    m.market_normalized,
    c.commodity_key,
    c.commodity_name,
    c.commodity_normalized,
    c.variety_name,
    c.variety_normalized,
    c.grade_name,
    c.grade_normalized,
    f.min_price,
    f.max_price,
    f.modal_price,
    f.price_unit,
    f.price_spread,
    f.price_spread_pct,
    f.quality_status,
    f.quality_warning_codes,
    f.first_loaded_run_id,
    f.last_loaded_run_id,
    f.last_loaded_at
FROM analytics.fact_mandi_prices AS f
JOIN analytics.dim_date AS d ON d.date_key = f.date_key
JOIN analytics.dim_market AS m ON m.market_key = f.market_key
JOIN analytics.dim_location AS l ON l.location_key = m.location_key
JOIN analytics.dim_commodity AS c ON c.commodity_key = f.commodity_key;

CREATE OR REPLACE VIEW analytics.vw_dashboard_price_trends AS
WITH daily_market_price AS (
    SELECT
        date_key,
        market_date,
        state_name,
        state_normalized,
        district_name,
        district_normalized,
        market_key,
        market_name,
        market_normalized,
        commodity_key,
        commodity_name,
        commodity_normalized,
        variety_name,
        variety_normalized,
        grade_name,
        grade_normalized,
        price_unit,
        AVG(min_price) AS avg_min_price,
        AVG(max_price) AS avg_max_price,
        AVG(modal_price) AS avg_modal_price,
        AVG(price_spread) AS avg_price_spread,
        AVG(price_spread_pct) AS avg_price_spread_pct,
        COUNT(*) AS observation_count,
        COUNT(*) FILTER (WHERE quality_status = 'suspicious') AS suspicious_observation_count
    FROM analytics.vw_mandi_price_observations
    GROUP BY
        date_key,
        market_date,
        state_name,
        state_normalized,
        district_name,
        district_normalized,
        market_key,
        market_name,
        market_normalized,
        commodity_key,
        commodity_name,
        commodity_normalized,
        variety_name,
        variety_normalized,
        grade_name,
        grade_normalized,
        price_unit
)
SELECT
    daily_market_price.*,
    AVG(avg_modal_price) OVER (
        PARTITION BY market_key, commodity_key
        ORDER BY market_date
        RANGE BETWEEN INTERVAL '6 days' PRECEDING AND CURRENT ROW
    ) AS modal_price_7d_moving_avg,
    AVG(avg_modal_price) OVER (
        PARTITION BY market_key, commodity_key
        ORDER BY market_date
        RANGE BETWEEN INTERVAL '29 days' PRECEDING AND CURRENT ROW
    ) AS modal_price_30d_moving_avg,
    LAG(avg_modal_price) OVER (
        PARTITION BY market_key, commodity_key
        ORDER BY market_date
    ) AS prior_reporting_day_modal_price
FROM daily_market_price;

CREATE OR REPLACE VIEW analytics.vw_dashboard_latest_market_comparison AS
WITH ranked_prices AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY o.market_key, o.commodity_key
            ORDER BY o.market_date DESC, o.mandi_price_key DESC
        ) AS market_recency_rank
    FROM analytics.vw_mandi_price_observations AS o
),
latest_market_prices AS (
    SELECT *
    FROM ranked_prices
    WHERE market_recency_rank = 1
),
benchmarked AS (
    SELECT
        latest_market_prices.*,
        AVG(modal_price) OVER (
            PARTITION BY state_normalized, commodity_normalized, variety_normalized, grade_normalized
        ) AS state_average_modal_price,
        AVG(modal_price) OVER (
            PARTITION BY state_normalized, district_normalized, commodity_normalized,
            variety_normalized, grade_normalized
        ) AS district_average_modal_price
    FROM latest_market_prices
)
SELECT
    benchmarked.*,
    modal_price - state_average_modal_price AS difference_from_state_average,
    modal_price - district_average_modal_price AS difference_from_district_average,
    DENSE_RANK() OVER (
        PARTITION BY state_normalized, commodity_normalized, variety_normalized, grade_normalized
        ORDER BY modal_price DESC
    ) AS state_modal_price_rank
FROM benchmarked;

CREATE OR REPLACE VIEW analytics.vw_dashboard_volatility AS
SELECT
    commodity_key,
    commodity_name,
    commodity_normalized,
    variety_name,
    variety_normalized,
    grade_name,
    grade_normalized,
    price_unit,
    MIN(market_date) AS first_reporting_date,
    MAX(market_date) AS latest_reporting_date,
    COUNT(*) AS observation_count,
    COUNT(DISTINCT market_key) AS reporting_mandi_count,
    AVG(modal_price) AS average_modal_price,
    STDDEV_SAMP(modal_price) AS modal_price_stddev,
    CASE
        WHEN AVG(modal_price) = 0 THEN NULL
        ELSE STDDEV_SAMP(modal_price) / AVG(modal_price) * 100
    END AS modal_price_coefficient_of_variation_pct,
    MIN(modal_price) AS minimum_modal_price,
    MAX(modal_price) AS maximum_modal_price,
    AVG(price_spread) AS average_price_spread,
    AVG(price_spread_pct) AS average_price_spread_pct,
    COUNT(*) FILTER (WHERE quality_status = 'suspicious') AS suspicious_observation_count
FROM analytics.vw_mandi_price_observations
GROUP BY
    commodity_key,
    commodity_name,
    commodity_normalized,
    variety_name,
    variety_normalized,
    grade_name,
    grade_normalized,
    price_unit;

CREATE OR REPLACE VIEW analytics.vw_dashboard_market_freshness AS
WITH latest_market_report AS (
    SELECT
        market_key,
        MAX(market_date) AS latest_market_date,
        COUNT(*) AS observation_count
    FROM analytics.vw_mandi_price_observations
    GROUP BY market_key
),
latest_successful_run AS (
    SELECT run_id
    FROM analytics.pipeline_run_log
    WHERE status = 'succeeded'
    ORDER BY completed_at DESC NULLS LAST, started_at DESC
    LIMIT 1
)
SELECT
    l.state_name,
    l.state_normalized,
    l.district_name,
    l.district_normalized,
    m.market_key,
    m.market_name,
    m.market_normalized,
    latest_market_report.latest_market_date,
    CURRENT_DATE - latest_market_report.latest_market_date AS days_since_latest_report,
    latest_market_report.observation_count,
    EXISTS (
        SELECT 1
        FROM analytics.data_quality_log AS quality
        JOIN latest_successful_run AS run ON run.run_id = quality.run_id
        WHERE quality.issue_code = 'stale_market'
          AND quality.source_observation_hash IN (
              SELECT source_observation_hash
              FROM analytics.fact_mandi_prices AS fact
              WHERE fact.market_key = m.market_key
          )
    ) AS flagged_stale_in_latest_run
FROM latest_market_report
JOIN analytics.dim_market AS m ON m.market_key = latest_market_report.market_key
JOIN analytics.dim_location AS l ON l.location_key = m.location_key;

CREATE OR REPLACE VIEW analytics.vw_dashboard_reporting_coverage AS
WITH reporting_series AS (
    SELECT
        state_name,
        state_normalized,
        district_name,
        district_normalized,
        market_key,
        market_name,
        market_normalized,
        commodity_key,
        commodity_name,
        commodity_normalized,
        variety_name,
        variety_normalized,
        grade_name,
        grade_normalized,
        MIN(market_date) AS first_reporting_date,
        MAX(market_date) AS latest_reporting_date,
        COUNT(DISTINCT market_date) AS actual_reporting_days
    FROM analytics.vw_mandi_price_observations
    GROUP BY
        state_name,
        state_normalized,
        district_name,
        district_normalized,
        market_key,
        market_name,
        market_normalized,
        commodity_key,
        commodity_name,
        commodity_normalized,
        variety_name,
        variety_normalized,
        grade_name,
        grade_normalized
)
SELECT
    reporting_series.*,
    (latest_reporting_date - first_reporting_date + 1) AS expected_reporting_days,
    (latest_reporting_date - first_reporting_date + 1) - actual_reporting_days
        AS missing_reporting_days,
    CASE
        WHEN latest_reporting_date = first_reporting_date THEN 0::NUMERIC
        ELSE ((latest_reporting_date - first_reporting_date + 1) - actual_reporting_days)::NUMERIC
            / (latest_reporting_date - first_reporting_date + 1) * 100
    END AS missing_reporting_rate_pct
FROM reporting_series;

CREATE OR REPLACE VIEW analytics.vw_dashboard_data_quality AS
WITH issue_counts AS (
    SELECT
        run_id,
        COUNT(*) AS logged_issue_count,
        COUNT(*) FILTER (WHERE severity = 'error') AS error_issue_count,
        COUNT(*) FILTER (WHERE severity = 'warning') AS warning_issue_count,
        COUNT(*) FILTER (WHERE issue_code = 'duplicate_observation') AS duplicate_issue_count,
        COUNT(*) FILTER (WHERE issue_code = 'conflicting_observation')
            AS conflicting_issue_count,
        COUNT(*) FILTER (WHERE issue_code = 'suspicious_price_change')
            AS suspicious_price_issue_count,
        COUNT(*) FILTER (WHERE issue_code = 'stale_market') AS stale_market_issue_count,
        COUNT(*) FILTER (WHERE issue_code = 'missing_reporting_date')
            AS missing_reporting_date_issue_count
    FROM analytics.data_quality_log
    GROUP BY run_id
)
SELECT
    run.run_id,
    run.source_name,
    run.status,
    run.started_at,
    run.completed_at,
    run.raw_rows_received,
    run.valid_rows_loaded,
    run.invalid_rows_rejected,
    run.duplicates_removed,
    run.conflicting_observation_count,
    run.suspicious_price_count,
    run.missing_reporting_date_count,
    run.stale_market_count,
    run.data_freshness_date,
    run.fact_rows_affected,
    run.quality_issues_logged,
    COALESCE(issue_counts.logged_issue_count, 0) AS logged_issue_count,
    COALESCE(issue_counts.error_issue_count, 0) AS error_issue_count,
    COALESCE(issue_counts.warning_issue_count, 0) AS warning_issue_count,
    COALESCE(issue_counts.duplicate_issue_count, 0) AS duplicate_issue_count,
    COALESCE(issue_counts.conflicting_issue_count, 0) AS conflicting_issue_count,
    COALESCE(issue_counts.suspicious_price_issue_count, 0) AS suspicious_price_issue_count,
    COALESCE(issue_counts.stale_market_issue_count, 0) AS stale_market_issue_count,
    COALESCE(issue_counts.missing_reporting_date_issue_count, 0)
        AS missing_reporting_date_issue_count
FROM analytics.pipeline_run_log AS run
LEFT JOIN issue_counts ON issue_counts.run_id = run.run_id;
