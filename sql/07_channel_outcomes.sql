-- Channel quality measured on outcomes, not on the score.
-- The score uses the channel as an input, so "% sent to Sales" partly reflects our own rules.
-- Comparing it with the (simulated) conversion rate shows which channels the rules over- or
-- under-value: a gap means the channel weight in config.yaml should be recalibrated.
WITH per_channel AS (
    SELECT
        e.source_channel,
        COUNT(*)                                             AS signups,
        SUM(CASE WHEN s.routed_to = 'crm' THEN 1 ELSE 0 END) AS sent_to_sales,
        SUM(o.converted)                                     AS conversions
    FROM events e
    JOIN scored_leads s ON s.message_id = e.message_id
    JOIN outcomes o     ON o.siren = e.siren
    GROUP BY e.source_channel
)
SELECT
    source_channel,
    signups,
    ROUND(100.0 * sent_to_sales / signups, 1) AS sent_to_sales_pct,
    ROUND(100.0 * conversions / signups, 1)   AS conversion_pct,
    RANK() OVER (ORDER BY 1.0 * sent_to_sales / signups DESC) AS rank_by_score,
    RANK() OVER (ORDER BY 1.0 * conversions / signups DESC)   AS rank_by_outcome
FROM per_channel
ORDER BY conversion_pct DESC;
