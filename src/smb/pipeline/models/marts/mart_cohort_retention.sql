-- Weekly signup-cohort retention for known (CRM) customers.
-- Answers "which customer cohorts have the strongest retention?".
WITH cohort AS (
  SELECT
    customer_id,
    signup_date,
    date_trunc('week', signup_date) AS cohort_week
  FROM stg_crm_customers
),
activity AS (
  SELECT DISTINCT
    s.customer_id,
    date_diff('week', c.signup_date, s.session_date) AS weeks_since_signup
  FROM int_sessions s
  JOIN cohort c USING (customer_id)
  WHERE s.customer_id IS NOT NULL
    AND s.session_date >= c.signup_date
),
sizes AS (
  SELECT cohort_week, count(*) AS cohort_size FROM cohort GROUP BY cohort_week
)
SELECT
  c.cohort_week,
  sz.cohort_size,
  a.weeks_since_signup,
  count(DISTINCT a.customer_id)                                        AS retained_customers,
  round(count(DISTINCT a.customer_id)::DOUBLE / sz.cohort_size, 4)     AS retention_rate
FROM activity a
JOIN cohort c USING (customer_id)
JOIN sizes sz ON sz.cohort_week = c.cohort_week
WHERE a.weeks_since_signup BETWEEN 0 AND 12
GROUP BY c.cohort_week, sz.cohort_size, a.weeks_since_signup
ORDER BY c.cohort_week, a.weeks_since_signup
