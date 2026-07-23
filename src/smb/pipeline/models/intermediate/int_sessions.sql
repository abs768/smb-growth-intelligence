-- Sessionized grain: one row per GA session with funnel flags and revenue.
-- This is the backbone for funnel, campaign and customer marts.
SELECT
  ga_session_id,
  any_value(user_pseudo_id)                                              AS user_pseudo_id,
  max(customer_id)                                                       AS customer_id,
  any_value(device_category)                                            AS device_category,
  any_value(country)                                                    AS country,
  any_value(campaign_id)                                               AS campaign_id,
  any_value(traffic_source)                                            AS traffic_source,
  min(event_timestamp)                                                 AS session_start_ts,
  max(event_timestamp)                                                 AS session_end_ts,
  min(event_date)                                                      AS session_date,
  count(*)                                                             AS event_count,
  max(CASE WHEN event_name = 'view_item'      THEN 1 ELSE 0 END)       AS did_view,
  max(CASE WHEN event_name = 'add_to_cart'    THEN 1 ELSE 0 END)       AS did_add_to_cart,
  max(CASE WHEN event_name = 'begin_checkout' THEN 1 ELSE 0 END)       AS did_checkout,
  max(CASE WHEN event_name = 'purchase'       THEN 1 ELSE 0 END)       AS did_purchase,
  count(DISTINCT CASE WHEN event_name = 'view_item' THEN item_id END)  AS products_viewed,
  coalesce(sum(CASE WHEN event_name = 'purchase' THEN purchase_revenue ELSE 0 END), 0) AS revenue
FROM stg_events
GROUP BY ga_session_id
