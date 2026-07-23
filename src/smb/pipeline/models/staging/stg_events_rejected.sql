-- Quarantine zone: rows that fail structural validation are captured here (not dropped
-- silently) so the data-quality layer can report a real "% bad records quarantined".
WITH src AS (
  SELECT * FROM read_parquet('data/raw/events/events.parquet')
)
SELECT
  *,
  CASE
    WHEN user_pseudo_id IS NULL THEN 'null_user_id'
    WHEN event_name = 'purchase' AND (purchase_revenue IS NULL OR purchase_revenue <= 0)
      THEN 'non_positive_revenue'
  END AS reject_reason
FROM src
WHERE user_pseudo_id IS NULL
   OR (event_name = 'purchase' AND (purchase_revenue IS NULL OR purchase_revenue <= 0))
