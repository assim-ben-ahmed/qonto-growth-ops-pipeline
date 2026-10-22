-- Lead score distribution in 10-point buckets, with a running total.
-- Question for Growth/Sales: if we move the threshold, how many leads does Sales get?
-- "leads_at_or_above" answers that directly (window function over descending buckets).
WITH buckets AS (
    SELECT
        (score / 10) * 10 AS score_bucket,
        COUNT(*)          AS leads
    FROM scored_leads
    GROUP BY score_bucket
)
SELECT
    score_bucket,
    score_bucket || '-' || (score_bucket + 9)                     AS bucket_label,
    leads,
    SUM(leads) OVER (ORDER BY score_bucket DESC
                     ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS leads_at_or_above
FROM buckets
ORDER BY score_bucket;
