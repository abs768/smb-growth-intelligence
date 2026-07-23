-- Daily advertising spend per campaign.
SELECT
  CAST(date AS DATE)     AS spend_date,
  campaign_id,
  channel,
  source,
  CAST(impressions AS BIGINT) AS impressions,
  CAST(clicks AS BIGINT)      AS clicks,
  CAST(cost AS DOUBLE)        AS cost
FROM read_parquet('data/raw/ad_spend/ad_spend.parquet')
