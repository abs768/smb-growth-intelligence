-- Campaign efficiency: spend vs. sessions, conversions, revenue, CAC and ROAS.
-- Answers "which traffic sources / campaigns drive high-value customers?".
WITH spend AS (
  SELECT campaign_id, any_value(channel) AS channel,
         sum(cost) AS spend, sum(impressions) AS impressions, sum(clicks) AS clicks
  FROM stg_ad_spend
  GROUP BY campaign_id
),
sess AS (
  SELECT
    campaign_id,
    count(*)                 AS sessions,
    sum(did_purchase)        AS buyers,
    sum(revenue)             AS revenue,
    count(DISTINCT user_pseudo_id) AS users
  FROM int_sessions
  GROUP BY campaign_id
)
SELECT
  se.campaign_id,
  sp.channel,
  sp.spend,
  se.sessions,
  se.users,
  se.buyers,
  se.revenue,
  round(se.buyers::DOUBLE / nullif(se.sessions, 0), 4)      AS conversion_rate,
  round(sp.spend / nullif(se.buyers, 0), 2)                 AS cac,
  round(se.revenue / nullif(sp.spend, 0), 2)               AS roas,
  round(sp.spend / nullif(se.sessions, 0), 3)              AS cost_per_session,
  round(se.revenue / nullif(se.buyers, 0), 2)             AS revenue_per_buyer
FROM sess se
LEFT JOIN spend sp USING (campaign_id)
ORDER BY se.revenue DESC
