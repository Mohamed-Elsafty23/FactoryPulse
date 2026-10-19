-- FactoryPulse operational monitoring queries.
-- Register the Delta ops path as the `ops` view/table before running locally.

-- ALERT 1: recent pipeline failures.
SELECT pipeline, run_id, started_at, error_message
FROM ops
WHERE status = 'failed'
ORDER BY started_at DESC
LIMIT 5;

-- ALERT 2: newest measured data freshness.
SELECT pipeline, started_at, ROUND(freshness_s / 3600, 2) AS freshness_hours
FROM ops
WHERE freshness_s IS NOT NULL
ORDER BY started_at DESC
LIMIT 1;

-- TREND: runtime degradation by pipeline stage.
SELECT
    pipeline,
    COUNT(*) AS runs,
    ROUND(AVG(duration_s), 1) AS avg_s,
    ROUND(MAX(duration_s), 1) AS max_s,
    ROUND(AVG(rows_written)) AS avg_rows
FROM ops
WHERE status = 'success'
GROUP BY pipeline
ORDER BY avg_s DESC;

-- TREND: Silver rejection rate by day.
SELECT
    DATE(started_at) AS day,
    SUM(rows_rejected) AS rejected,
    SUM(rows_read) AS read,
    ROUND(100.0 * SUM(rows_rejected) / NULLIF(SUM(rows_read), 0), 2) AS pct
FROM ops
WHERE pipeline = 'silver'
GROUP BY DATE(started_at)
ORDER BY day DESC
LIMIT 7;
