-- Customer-level analytical features (RFM + engagement + funnel behaviour).
-- Recency is measured against the latest event date in the dataset.
WITH bounds AS (
  SELECT max(session_date) AS as_of_date FROM int_sessions
),
agg AS (
  SELECT
    s.user_pseudo_id,
    max(s.customer_id)                                              AS customer_id,
    any_value(s.device_category)                                   AS device_category,
    any_value(s.country)                                           AS country,
    mode(s.campaign_id)                                            AS primary_campaign,
    count(*)                                                       AS sessions,
    sum(s.did_purchase)                                            AS purchasing_sessions,
    sum(s.did_add_to_cart)                                         AS cart_sessions,
    sum(s.revenue)                                                 AS monetary,
    sum(s.event_count)                                             AS total_events,
    max(s.products_viewed)                                         AS max_products_viewed,
    min(s.session_date)                                            AS first_seen,
    max(s.session_date)                                            AS last_seen
  FROM int_sessions s
  GROUP BY s.user_pseudo_id
)
SELECT
  a.user_pseudo_id,
  a.customer_id,
  (a.customer_id IS NOT NULL)                                      AS is_known_customer,
  a.device_category,
  a.country,
  a.primary_campaign,
  a.sessions,
  a.purchasing_sessions,
  datediff('day', a.last_seen, b.as_of_date)                       AS recency_days,
  a.monetary,
  a.total_events,
  CASE WHEN a.purchasing_sessions > 0
       THEN a.monetary / a.purchasing_sessions ELSE 0 END          AS avg_order_value,
  CASE WHEN a.sessions > 0
       THEN a.purchasing_sessions::DOUBLE / a.sessions ELSE 0 END  AS conversion_rate,
  CASE WHEN a.cart_sessions > 0
       THEN 1 - (a.purchasing_sessions::DOUBLE / a.cart_sessions) ELSE 0 END AS funnel_abandon_rate,
  datediff('day', a.first_seen, a.last_seen)                       AS tenure_days,
  (a.monetary > 0)                                                 AS has_purchased
FROM agg a
CROSS JOIN bounds b
