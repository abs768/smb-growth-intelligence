-- Clean, deduplicated event stream.
-- Rejects rows with a null user id or a non-positive purchase revenue (those land in
-- stg_events_rejected), then deduplicates on event_id keeping the earliest occurrence.
WITH src AS (
  SELECT * FROM read_parquet('data/raw/events/events.parquet')
),
valid AS (
  SELECT *
  FROM src
  WHERE user_pseudo_id IS NOT NULL
    AND NOT (event_name = 'purchase' AND (purchase_revenue IS NULL OR purchase_revenue <= 0))
),
ranked AS (
  SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY event_timestamp) AS rn
  FROM valid
)
SELECT
  event_id,
  event_timestamp,
  CAST(event_date AS DATE)          AS event_date,
  event_name,
  user_pseudo_id,
  customer_id,
  ga_session_id,
  device_category,
  country,
  campaign_id,
  traffic_source,
  traffic_medium,
  item_id,
  item_category,
  item_name,
  CAST(quantity AS INTEGER)         AS quantity,
  CAST(purchase_revenue AS DOUBLE)  AS purchase_revenue
FROM ranked
WHERE rn = 1
