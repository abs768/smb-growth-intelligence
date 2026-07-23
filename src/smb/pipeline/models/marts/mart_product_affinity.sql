-- Product view-to-purchase efficiency. Answers "which products are frequently viewed
-- but rarely purchased?" (candidates for merchandising / pricing action).
WITH per_item AS (
  SELECT
    item_id,
    any_value(item_name)     AS item_name,
    any_value(item_category) AS item_category,
    sum(CASE WHEN event_name = 'view_item'   THEN 1 ELSE 0 END) AS views,
    sum(CASE WHEN event_name = 'add_to_cart' THEN 1 ELSE 0 END) AS carts,
    sum(CASE WHEN event_name = 'purchase'    THEN 1 ELSE 0 END) AS purchases,
    coalesce(sum(CASE WHEN event_name = 'purchase' THEN purchase_revenue END), 0) AS revenue
  FROM stg_events
  WHERE item_id IS NOT NULL
  GROUP BY item_id
)
SELECT
  item_id,
  item_name,
  item_category,
  views,
  carts,
  purchases,
  revenue,
  round(purchases::DOUBLE / nullif(views, 0), 4) AS view_to_purchase_rate,
  round(carts::DOUBLE     / nullif(views, 0), 4) AS view_to_cart_rate,
  -- high traffic, weak conversion => merchandising opportunity
  (views >= 300 AND purchases::DOUBLE / nullif(views, 0) < 0.05) AS is_showcase_underperformer
FROM per_item
ORDER BY views DESC
