-- Top sectors among sign-ups, ranked with a window function.
-- Question for Growth: which industries should the next campaign target?
WITH sector_stats AS (
    SELECT
        COALESCE(c.sector_label, 'Unknown')                    AS sector,
        COUNT(*)                                               AS signups,
        SUM(CASE WHEN s.routed_to = 'crm' THEN 1 ELSE 0 END)   AS hot_leads,
        ROUND(AVG(s.score), 1)                                 AS avg_score
    FROM scored_leads s
    JOIN companies c ON c.siren = s.siren
    GROUP BY sector
)
SELECT
    RANK() OVER (ORDER BY signups DESC)                        AS rank_by_volume,
    sector,
    signups,
    hot_leads,
    avg_score,
    ROUND(100.0 * signups / SUM(signups) OVER (), 1)           AS share_of_signups_pct
FROM sector_stats
ORDER BY rank_by_volume
LIMIT 10;
