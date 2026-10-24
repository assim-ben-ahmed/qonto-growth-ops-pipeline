-- Website funnel by channel: visited -> viewed pricing -> started sign-up -> signed up.
-- Question for Growth: where do visitors drop off, and does it depend on the channel?
-- Built from raw Segment calls: one row per anonymous visitor, then one row per step.
WITH visitors AS (
    SELECT
        anonymous_id,
        MAX(CASE WHEN name = 'Landing' THEN channel END)          AS channel,  -- first touch
        MAX(CASE WHEN name = 'Pricing' THEN 1 ELSE 0 END)           AS viewed_pricing,
        MAX(CASE WHEN name = 'Signup Started' THEN 1 ELSE 0 END)    AS started_signup,
        MAX(CASE WHEN name = 'Account Signed Up' THEN 1 ELSE 0 END) AS signed_up
    FROM web_events
    GROUP BY anonymous_id
),
steps AS (
    SELECT channel, 1 AS step_order, 'Visited' AS step, COUNT(*) AS visitors FROM visitors GROUP BY channel
    UNION ALL
    SELECT channel, 2, 'Viewed pricing', SUM(viewed_pricing) FROM visitors GROUP BY channel
    UNION ALL
    SELECT channel, 3, 'Started sign-up', SUM(started_signup) FROM visitors GROUP BY channel
    UNION ALL
    SELECT channel, 4, 'Signed up', SUM(signed_up) FROM visitors GROUP BY channel
)
SELECT
    channel,
    step_order,
    step,
    visitors,
    -- share of the channel's visitors still there at this step
    ROUND(100.0 * visitors / FIRST_VALUE(visitors) OVER (PARTITION BY channel ORDER BY step_order), 1)
        AS pct_of_visitors,
    -- conversion from the previous step (NULL for the first step)
    ROUND(100.0 * visitors / LAG(visitors) OVER (PARTITION BY channel ORDER BY step_order), 1)
        AS step_conversion_pct
FROM steps
ORDER BY channel, step_order;
