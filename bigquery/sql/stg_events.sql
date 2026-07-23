-- BigQuery staging model: flatten Google's public GA4 export into the same event shape
-- the local DuckDB prototype uses. This is the real GCP-side equivalent of
-- src/smb/pipeline/models/staging/stg_events.sql.
--
-- Source: `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
--   (3 months of obfuscated Google Merchandise Store ecommerce events).
--
-- Run it in a free BigQuery sandbox; partition-prune with the _TABLE_SUFFIX filter to keep
-- bytes scanned (and therefore cost) low.

CREATE OR REPLACE TABLE `smb_growth.stg_events`
PARTITION BY event_date
CLUSTER BY event_name AS
WITH flattened AS (
  SELECT
    -- deterministic surrogate event id (GA4 has no native one)
    TO_HEX(MD5(CONCAT(
      user_pseudo_id, CAST(event_timestamp AS STRING), event_name,
      COALESCE((SELECT CAST(value.int_value AS STRING) FROM UNNEST(event_params)
                WHERE key = 'ga_session_id'), '')
    ))) AS event_id,
    TIMESTAMP_MICROS(event_timestamp)                                    AS event_timestamp,
    PARSE_DATE('%Y%m%d', event_date)                                     AS event_date,
    event_name,
    user_pseudo_id,
    user_id                                                              AS customer_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
    device.category                                                      AS device_category,
    geo.country                                                          AS country,
    traffic_source.name                                                  AS campaign_id,
    traffic_source.source                                                AS traffic_source,
    traffic_source.medium                                                AS traffic_medium,
    (SELECT i.item_id   FROM UNNEST(items) i LIMIT 1)                    AS item_id,
    (SELECT i.item_category FROM UNNEST(items) i LIMIT 1)                AS item_category,
    (SELECT i.item_name FROM UNNEST(items) i LIMIT 1)                    AS item_name,
    (SELECT SUM(i.quantity) FROM UNNEST(items) i)                        AS quantity,
    ecommerce.purchase_revenue_in_usd                                    AS purchase_revenue
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  -- narrow the scan window to control cost; widen for a full backfill
  WHERE _TABLE_SUFFIX BETWEEN '20210101' AND '20210131'
),
valid AS (
  SELECT * FROM flattened
  WHERE user_pseudo_id IS NOT NULL
    AND NOT (event_name = 'purchase' AND (purchase_revenue IS NULL OR purchase_revenue <= 0))
),
deduped AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY event_id ORDER BY event_timestamp) AS rn
  FROM valid
)
SELECT * EXCEPT (rn) FROM deduped WHERE rn = 1;
