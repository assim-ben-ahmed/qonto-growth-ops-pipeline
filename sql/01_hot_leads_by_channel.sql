-- Hot leads by acquisition channel.
-- Question for Growth: which channels bring sign-ups that Sales actually wants?
-- Uses a CTE to compute per-channel totals before the conversion rate.
WITH channel_stats AS (
    SELECT
        e.source_channel,
        COUNT(*)                                          AS signups,
        SUM(CASE WHEN s.routed_to = 'crm' THEN 1 ELSE 0 END) AS hot_leads,
        ROUND(AVG(s.score), 1)                            AS avg_score
    FROM events e
    JOIN scored_leads s ON s.message_id = e.message_id
    GROUP BY e.source_channel
)
SELECT
    source_channel,
    signups,
    hot_leads,
    ROUND(100.0 * hot_leads / signups, 1) AS hot_rate_pct,
    avg_score
FROM channel_stats
ORDER BY hot_rate_pct DESC;
