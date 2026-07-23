-- CRM customer master.
SELECT
  customer_id,
  CAST(signup_date AS DATE) AS signup_date,
  plan,
  region
FROM read_parquet('data/raw/crm_customers/crm_customers.parquet')
