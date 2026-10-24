-- Sign-ups by company age bucket.
-- Question for Growth: are we acquiring brand-new businesses (creation = onboarding flow)
-- or established SMEs switching banks (= migration / multi-user pitch)?
-- conversion_pct (simulated outcomes) shows whether the age rule in the score is right.
WITH aged AS (
    SELECT
        s.routed_to,
        o.converted,
        CASE
            WHEN c.company_age_years IS NULL THEN '5. Unknown'
            WHEN c.company_age_years < 1     THEN '1. < 1 year'
            WHEN c.company_age_years < 3     THEN '2. 1-3 years'
            WHEN c.company_age_years < 10    THEN '3. 3-10 years'
            ELSE                                  '4. 10+ years'
        END AS age_bucket
    FROM scored_leads s
    JOIN companies c     ON c.siren = s.siren
    LEFT JOIN outcomes o ON o.siren = s.siren
)
SELECT
    age_bucket,
    COUNT(*)                                             AS signups,
    SUM(CASE WHEN routed_to = 'crm' THEN 1 ELSE 0 END)   AS hot_leads,
    SUM(CASE WHEN routed_to = 'braze' THEN 1 ELSE 0 END) AS nurture,
    ROUND(100.0 * AVG(converted), 1)                     AS conversion_pct
FROM aged
GROUP BY age_bucket
ORDER BY age_bucket;
