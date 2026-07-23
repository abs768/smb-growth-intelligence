-- Funnel drop-off by traffic source. Answers "where are customers abandoning the funnel?"
-- and "which traffic sources drive high-value customers?".
WITH by_source AS (
  SELECT
    traffic_source,
    count(*)               AS sessions,
    sum(did_view)          AS view_item,
    sum(did_add_to_cart)   AS add_to_cart,
    sum(did_checkout)      AS begin_checkout,
    sum(did_purchase)      AS purchase,
    sum(revenue)           AS revenue
  FROM int_sessions
  GROUP BY traffic_source
),
unioned AS (
  SELECT * FROM by_source
  UNION ALL
  SELECT 'ALL', sum(sessions), sum(view_item), sum(add_to_cart),
         sum(begin_checkout), sum(purchase), sum(revenue)
  FROM by_source
)
SELECT
  traffic_source,
  sessions,
  view_item,
  add_to_cart,
  begin_checkout,
  purchase,
  revenue,
  round(view_item::DOUBLE      / nullif(sessions, 0), 4)        AS view_rate,
  round(add_to_cart::DOUBLE    / nullif(view_item, 0), 4)       AS view_to_cart_rate,
  round(begin_checkout::DOUBLE / nullif(add_to_cart, 0), 4)     AS cart_to_checkout_rate,
  round(purchase::DOUBLE       / nullif(begin_checkout, 0), 4)  AS checkout_to_purchase_rate,
  round(purchase::DOUBLE       / nullif(sessions, 0), 4)        AS overall_conversion_rate
FROM unioned
ORDER BY (traffic_source = 'ALL'), sessions DESC
