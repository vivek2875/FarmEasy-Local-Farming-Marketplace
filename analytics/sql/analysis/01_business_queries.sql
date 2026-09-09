-- FarmEasy Mandi Price and Supply Intelligence: business-analysis queries.
-- Replace :named_parameters with safely bound values in a SQL client, BI tool,
-- or API repository. Do not concatenate user input into these statements.

-- Query 01
-- Business question: Which currently fresh mandi offers the highest modal price for a selected commodity?
-- Why it matters: It creates a shortlist for a farmer before transport, quality, fees, and quantity are evaluated.
-- Expected interpretation: A high rank is a price signal, not a guaranteed net-profit recommendation.
WITH eligible_markets AS (
    SELECT *
    FROM analytics.vw_dashboard_latest_market_comparison
    WHERE commodity_normalized = :commodity_normalized
      AND market_date >= CURRENT_DATE - (:max_age_days * INTERVAL '1 day')
      AND quality_status <> 'suspicious'
)
SELECT
    state_name,
    district_name,
    market_name,
    variety_name,
    grade_name,
    market_date,
    modal_price,
    price_unit,
    price_spread,
    price_spread_pct,
    difference_from_district_average,
    state_modal_price_rank,
    DENSE_RANK() OVER (ORDER BY modal_price DESC) AS best_mandi_rank,
    'Compare transport, handling, fees, grade, and sale quantity before choosing a mandi.'
        AS decision_note
FROM eligible_markets
ORDER BY modal_price DESC, market_date DESC, market_name;

-- Query 02
-- Business question: How do modal prices compare between districts and states for a commodity in a date range?
-- Why it matters: Regional benchmarking shows whether a local market is broadly competitive or an outlier.
-- Expected interpretation: Differences can reflect quality/variety mix as well as geography, so compare like-for-like grades.
SELECT
    state_name,
    district_name,
    COUNT(*) AS observation_count,
    COUNT(DISTINCT market_key) AS active_mandi_count,
    ROUND(AVG(modal_price), 2) AS average_modal_price,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY modal_price)::NUMERIC, 2)
        AS median_modal_price,
    MIN(modal_price) AS minimum_modal_price,
    MAX(modal_price) AS maximum_modal_price
FROM analytics.vw_mandi_price_observations
WHERE commodity_normalized = :commodity_normalized
  AND market_date BETWEEN :start_date AND :end_date
GROUP BY state_name, district_name
ORDER BY average_modal_price DESC, active_mandi_count DESC;

-- Query 03
-- Business question: How has a selected mandi/commodity changed over seven, thirty, and ninety calendar days?
-- Why it matters: Time windows separate a short movement from a persistent price trend.
-- Expected interpretation: Moving averages use available reports only; a missing report is not interpreted as zero price.
WITH selected_series AS (
    SELECT
        market_date,
        market_name,
        commodity_name,
        variety_name,
        grade_name,
        avg_modal_price,
        modal_price_7d_moving_avg,
        modal_price_30d_moving_avg
    FROM analytics.vw_dashboard_price_trends
    WHERE market_normalized = :market_normalized
      AND commodity_normalized = :commodity_normalized
      AND market_date >= CURRENT_DATE - INTERVAL '90 days'
)
SELECT *
FROM selected_series
ORDER BY market_date;

-- Query 04
-- Business question: Which commodity/variety/grade combinations are most volatile across reporting mandis?
-- Why it matters: High volatility indicates higher timing risk and deserves closer monitoring before a sale decision.
-- Expected interpretation: The coefficient of variation compares volatility fairly across price levels; inspect sample size too.
SELECT
    commodity_name,
    variety_name,
    grade_name,
    reporting_mandi_count,
    observation_count,
    average_modal_price,
    modal_price_stddev,
    modal_price_coefficient_of_variation_pct,
    suspicious_observation_count
FROM analytics.vw_dashboard_volatility
WHERE observation_count >= :minimum_observations
ORDER BY modal_price_coefficient_of_variation_pct DESC NULLS LAST, observation_count DESC
LIMIT :result_limit;

-- Query 05
-- Business question: Which individual mandis have the highest modal-price volatility for a selected commodity?
-- Why it matters: A commodity may be stable overall while a specific mandi remains risky due to local supply or reporting swings.
-- Expected interpretation: Compare coefficient of variation only where the mandi has enough observations to be meaningful.
SELECT
    state_name,
    district_name,
    market_name,
    COUNT(*) AS observation_count,
    AVG(modal_price) AS average_modal_price,
    STDDEV_SAMP(modal_price) AS modal_price_stddev,
    CASE
        WHEN AVG(modal_price) = 0 THEN NULL
        ELSE STDDEV_SAMP(modal_price) / AVG(modal_price) * 100
    END AS modal_price_coefficient_of_variation_pct,
    COUNT(*) FILTER (WHERE quality_status = 'suspicious') AS suspicious_observation_count
FROM analytics.vw_mandi_price_observations
WHERE commodity_normalized = :commodity_normalized
  AND market_date BETWEEN :start_date AND :end_date
GROUP BY state_name, district_name, market_name
HAVING COUNT(*) >= :minimum_observations
ORDER BY modal_price_coefficient_of_variation_pct DESC NULLS LAST;

-- Query 06
-- Business question: Which source observations have been flagged as abnormal price movements?
-- Why it matters: Analysts need to review potential reporting mistakes before treating a spike as a market opportunity.
-- Expected interpretation: A flag is a review queue, not proof that the government record is wrong.
WITH latest_successful_run AS (
    SELECT run_id
    FROM analytics.pipeline_run_log
    WHERE status = 'succeeded'
    ORDER BY completed_at DESC NULLS LAST, started_at DESC
    LIMIT 1
)
SELECT
    quality.created_at AS flagged_at,
    quality.reason,
    observation.market_date,
    observation.state_name,
    observation.district_name,
    observation.market_name,
    observation.commodity_name,
    observation.variety_name,
    observation.grade_name,
    observation.modal_price,
    observation.price_unit,
    observation.quality_warning_codes
FROM analytics.data_quality_log AS quality
JOIN latest_successful_run AS run ON run.run_id = quality.run_id
LEFT JOIN analytics.vw_mandi_price_observations AS observation
    ON observation.source_observation_hash = quality.source_observation_hash
WHERE quality.issue_code = 'suspicious_price_change'
ORDER BY flagged_at DESC, observation.market_date DESC;

-- Query 07
-- Business question: Which markets are stale or have recent reporting gaps?
-- Why it matters: A price comparison is unsafe when a mandi has stopped reporting or the data has coverage holes.
-- Expected interpretation: Days since report measures freshness; a stale flag reflects the last pipeline's configured threshold.
SELECT
    state_name,
    district_name,
    market_name,
    latest_market_date,
    days_since_latest_report,
    observation_count,
    flagged_stale_in_latest_run
FROM analytics.vw_dashboard_market_freshness
WHERE flagged_stale_in_latest_run
   OR days_since_latest_report > :freshness_threshold_days
ORDER BY days_since_latest_report DESC, state_name, district_name, market_name;

-- Query 08
-- Business question: How wide are the reported min–max price spreads by commodity and market?
-- Why it matters: A large spread can signal uneven quality, grade mix, or uncertainty around the quoted modal price.
-- Expected interpretation: Compare spread percentage as well as rupees because commodities have different price levels.
SELECT
    commodity_name,
    market_name,
    COUNT(*) AS observation_count,
    AVG(min_price) AS average_min_price,
    AVG(max_price) AS average_max_price,
    AVG(modal_price) AS average_modal_price,
    AVG(price_spread) AS average_price_spread,
    AVG(price_spread_pct) AS average_price_spread_pct,
    COUNT(*) FILTER (WHERE price_spread_pct >= :high_spread_pct) AS high_spread_observation_count
FROM analytics.vw_mandi_price_observations
WHERE market_date BETWEEN :start_date AND :end_date
GROUP BY commodity_name, market_name
HAVING COUNT(*) >= :minimum_observations
ORDER BY average_price_spread_pct DESC NULLS LAST;

-- Query 09
-- Business question: What was the week-over-week movement in state-level modal prices?
-- Why it matters: It highlights recent momentum without overreacting to one daily quote.
-- Expected interpretation: Positive values mean the latest reported weekly average rose versus the prior reported week.
WITH weekly_prices AS (
    SELECT
        state_name,
        commodity_name,
        DATE_TRUNC('week', market_date)::DATE AS week_start,
        AVG(modal_price) AS weekly_average_modal_price
    FROM analytics.vw_mandi_price_observations
    WHERE commodity_normalized = :commodity_normalized
      AND market_date BETWEEN :start_date AND :end_date
    GROUP BY state_name, commodity_name, DATE_TRUNC('week', market_date)::DATE
),
weekly_changes AS (
    SELECT
        weekly_prices.*,
        LAG(weekly_average_modal_price) OVER (
            PARTITION BY state_name, commodity_name
            ORDER BY week_start
        ) AS prior_week_average_modal_price
    FROM weekly_prices
)
SELECT
    *,
    weekly_average_modal_price - prior_week_average_modal_price AS week_over_week_change,
    CASE
        WHEN prior_week_average_modal_price = 0 THEN NULL
        ELSE (weekly_average_modal_price - prior_week_average_modal_price)
            / prior_week_average_modal_price * 100
    END AS week_over_week_change_pct
FROM weekly_changes
ORDER BY state_name, week_start;

-- Query 10
-- Business question: What is the month-over-month price movement for each state and commodity?
-- Why it matters: Monthly movement supports strategic selling discussions that are less noisy than daily comparisons.
-- Expected interpretation: Missing months remain absent; do not infer a zero-price month from lack of reporting.
WITH monthly_prices AS (
    SELECT
        state_name,
        commodity_name,
        DATE_TRUNC('month', market_date)::DATE AS month_start,
        AVG(modal_price) AS monthly_average_modal_price
    FROM analytics.vw_mandi_price_observations
    WHERE commodity_normalized = :commodity_normalized
    GROUP BY state_name, commodity_name, DATE_TRUNC('month', market_date)::DATE
),
monthly_changes AS (
    SELECT
        monthly_prices.*,
        LAG(monthly_average_modal_price) OVER (
            PARTITION BY state_name, commodity_name
            ORDER BY month_start
        ) AS prior_month_average_modal_price
    FROM monthly_prices
)
SELECT
    *,
    monthly_average_modal_price - prior_month_average_modal_price AS month_over_month_change,
    CASE
        WHEN prior_month_average_modal_price = 0 THEN NULL
        ELSE (monthly_average_modal_price - prior_month_average_modal_price)
            / prior_month_average_modal_price * 100
    END AS month_over_month_change_pct
FROM monthly_changes
ORDER BY state_name, month_start;

-- Query 11
-- Business question: What is the reporting completeness rate for active market/commodity combinations in a period?
-- Why it matters: It quantifies whether an apparent trend rests on broad reporting coverage or sparse observations.
-- Expected interpretation: This is a reporting-rate metric, not a supply or market-closure metric.
WITH calendar AS (
    SELECT day::DATE AS market_date
    FROM GENERATE_SERIES(CAST(:start_date AS DATE), CAST(:end_date AS DATE), INTERVAL '1 day')
        AS day
),
active_market_commodities AS (
    SELECT DISTINCT market_key, commodity_key
    FROM analytics.vw_mandi_price_observations
    WHERE market_date BETWEEN :start_date AND :end_date
),
expected_reports AS (
    SELECT COUNT(*) AS expected_report_count
    FROM active_market_commodities
    CROSS JOIN calendar
),
actual_reports AS (
    SELECT COUNT(DISTINCT (market_key, commodity_key, market_date)) AS actual_report_count
    FROM analytics.vw_mandi_price_observations
    WHERE market_date BETWEEN :start_date AND :end_date
)
SELECT
    expected_report_count,
    actual_report_count,
    expected_report_count - actual_report_count AS missing_report_count,
    CASE
        WHEN expected_report_count = 0 THEN NULL
        ELSE (expected_report_count - actual_report_count)::NUMERIC / expected_report_count * 100
    END AS missing_reporting_rate_pct
FROM expected_reports
CROSS JOIN actual_reports;

-- Query 12
-- Business question: How healthy was each pipeline run, including rejected, duplicate, suspicious, and stale records?
-- Why it matters: Executive dashboards need a trust signal before stakeholders act on price KPIs.
-- Expected interpretation: Compare the latest successful run with earlier runs to identify source or pipeline regressions.
SELECT
    run_id,
    source_name,
    completed_at,
    raw_rows_received,
    valid_rows_loaded,
    invalid_rows_rejected,
    duplicates_removed,
    conflicting_observation_count,
    suspicious_price_count,
    stale_market_count,
    missing_reporting_date_count,
    data_freshness_date,
    CASE
        WHEN raw_rows_received = 0 THEN NULL
        ELSE invalid_rows_rejected::NUMERIC / raw_rows_received * 100
    END AS rejected_row_rate_pct,
    error_issue_count,
    warning_issue_count
FROM analytics.vw_dashboard_data_quality
WHERE status = 'succeeded'
ORDER BY completed_at DESC NULLS LAST, started_at DESC;

-- Query 13
-- Business question: Which states have the broadest active mandi coverage for a selected commodity today?
-- Why it matters: Coverage helps a buyer or farmer distinguish a broad market comparison from a single-market signal.
-- Expected interpretation: More active mandis improves comparison depth but does not imply identical product quality.
WITH latest_date AS (
    SELECT MAX(market_date) AS market_date
    FROM analytics.vw_mandi_price_observations
    WHERE commodity_normalized = :commodity_normalized
)
SELECT
    observation.state_name,
    COUNT(DISTINCT observation.market_key) AS active_reporting_mandi_count,
    AVG(observation.modal_price) AS latest_average_modal_price,
    COUNT(*) FILTER (WHERE observation.quality_status = 'suspicious')
        AS suspicious_observation_count
FROM analytics.vw_mandi_price_observations AS observation
JOIN latest_date ON latest_date.market_date = observation.market_date
WHERE observation.commodity_normalized = :commodity_normalized
GROUP BY observation.state_name
ORDER BY active_reporting_mandi_count DESC, latest_average_modal_price DESC;

-- Query 14
-- Business question: Where is a mandi's latest modal price materially above its district benchmark?
-- Why it matters: It identifies market opportunities that deserve a logistics and quality-cost comparison.
-- Expected interpretation: A positive difference is not an automatic routing recommendation because transport and fees can erase it.
SELECT
    state_name,
    district_name,
    market_name,
    commodity_name,
    variety_name,
    grade_name,
    market_date,
    modal_price,
    district_average_modal_price,
    difference_from_district_average,
    price_spread_pct,
    state_modal_price_rank
FROM analytics.vw_dashboard_latest_market_comparison
WHERE commodity_normalized = :commodity_normalized
  AND difference_from_district_average >= :minimum_price_advantage
  AND quality_status <> 'suspicious'
ORDER BY difference_from_district_average DESC, market_date DESC;

-- Query 15
-- Business question: Which records deviate sharply from their own seven-day price pattern?
-- Why it matters: This gives analysts a second, explainable outlier screen in addition to the ingestion-time warning flag.
-- Expected interpretation: Review the source row and market context; seasonality or a genuine supply shock may explain the deviation.
SELECT
    market_date,
    state_name,
    district_name,
    market_name,
    commodity_name,
    variety_name,
    grade_name,
    avg_modal_price,
    modal_price_7d_moving_avg,
    CASE
        WHEN modal_price_7d_moving_avg = 0 THEN NULL
        ELSE (avg_modal_price - modal_price_7d_moving_avg) / modal_price_7d_moving_avg * 100
    END AS deviation_from_7d_average_pct,
    suspicious_observation_count
FROM analytics.vw_dashboard_price_trends
WHERE modal_price_7d_moving_avg IS NOT NULL
  AND ABS((avg_modal_price - modal_price_7d_moving_avg) / modal_price_7d_moving_avg * 100)
      >= :outlier_threshold_pct
ORDER BY ABS((avg_modal_price - modal_price_7d_moving_avg) / modal_price_7d_moving_avg * 100)
    DESC;

-- Query 16
-- Business question: What does the next observed modal price show after each market report?
-- Why it matters: Lead/lag analysis helps validate direction changes and supports chart annotations for price reversals.
-- Expected interpretation: The next value is the next available report, not necessarily the next calendar day.
SELECT
    market_date,
    state_name,
    district_name,
    market_name,
    commodity_name,
    modal_price,
    LEAD(modal_price) OVER (
        PARTITION BY market_key, commodity_key
        ORDER BY market_date
    ) AS next_reported_modal_price,
    LEAD(market_date) OVER (
        PARTITION BY market_key, commodity_key
        ORDER BY market_date
    ) AS next_reporting_date
FROM analytics.vw_mandi_price_observations
WHERE commodity_normalized = :commodity_normalized
  AND market_normalized = :market_normalized
ORDER BY market_date;

-- Query 17
-- Business question: Does the commodity/date filter use the warehouse's intended access path at production scale?
-- Why it matters: Slow analytical endpoints and dashboard refreshes undermine usability as history grows.
-- Expected interpretation: PostgreSQL should be able to use the commodity/date fact index after resolving the commodity dimension.
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    market_date,
    market_name,
    commodity_name,
    modal_price,
    price_spread_pct,
    quality_status
FROM analytics.vw_mandi_price_observations
WHERE commodity_normalized = :commodity_normalized
  AND market_date BETWEEN :start_date AND :end_date
ORDER BY market_date DESC, market_name;
