-- Does the score predict who converts? (outcomes are simulated - see src/outcomes.py)
-- Question for Growth/Sales: if Sales only calls the top 20% of scores,
-- what share of all future customers do they reach?
-- NTILE splits sign-ups into 5 equal groups by score; running SUM = cumulative capture.
WITH ranked AS (
    SELECT
        s.score,
        o.converted,
        NTILE(5) OVER (ORDER BY s.score DESC, s.siren) AS quintile
    FROM scored_leads s
    JOIN outcomes o ON o.siren = s.siren
),
by_quintile AS (
    SELECT
        quintile,
        COUNT(*)       AS signups,
        MIN(score)     AS min_score,
        MAX(score)     AS max_score,
        SUM(converted) AS conversions
    FROM ranked
    GROUP BY quintile
)
SELECT
    quintile,
    CASE quintile WHEN 1 THEN 'Top 20%'
                  ELSE ((quintile - 1) * 20) || '-' || (quintile * 20) || '%' END  -- () needed: || binds before *
        AS score_group,
    min_score || '-' || max_score                                  AS score_range,
    signups,
    conversions,
    ROUND(100.0 * conversions / signups, 1)                        AS conversion_pct,
    -- lift: conversion rate vs the average sign-up (1.0 = no better than random)
    ROUND((1.0 * conversions / signups)
          / (1.0 * SUM(conversions) OVER () / SUM(signups) OVER ()), 2) AS lift,
    ROUND(100.0 * SUM(conversions) OVER (ORDER BY quintile) / SUM(conversions) OVER (), 1)
        AS cum_share_of_conversions_pct
FROM by_quintile
ORDER BY quintile;
