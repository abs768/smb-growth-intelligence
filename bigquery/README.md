# GCP / BigQuery build (the "week 2+" path)

The local prototype (`make all`) runs the **identical modeling logic** on DuckDB so it works
offline at zero cost. This folder is the GCP-native counterpart: the same staging → mart layers
and the same assertions, expressed against Google's real public GA4 dataset with Dataform.

## Source data

`bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` — three months of obfuscated
Google Merchandise Store ecommerce events, available through BigQuery Public Datasets. No copy
or download required; you query it in place.

## Run it in a free BigQuery sandbox

1. Create a GCP project and open the BigQuery sandbox (no billing card required).
2. Create the target dataset: `bq mk --location=US smb_growth`.
3. Run `bigquery/sql/stg_events.sql` in the console. The `_TABLE_SUFFIX BETWEEN ...` filter
   keeps the scan to a single month so you stay inside the sandbox's free 1 TB/month.
4. Point Looker Studio at the resulting `smb_growth.mart_*` tables for the dashboards.

## Cost guardrails (important)

- Every model is **partitioned** (`event_date`) and **clustered** (`event_name`) so downstream
  queries prune bytes scanned.
- Staging filters `_TABLE_SUFFIX` to bound the date range — widen it deliberately, not by default.
- Set a billing budget alert before running the wider backfill.

## Local → GCP mapping

| Concern            | Local prototype (this repo)        | GCP build (this folder)                |
|--------------------|------------------------------------|----------------------------------------|
| Raw zone           | `data/raw/*.parquet`               | Cloud Storage / GA4 public dataset     |
| Warehouse          | DuckDB (`data/warehouse.duckdb`)   | BigQuery (`smb_growth` dataset)        |
| Transformations    | SQL runner (`run_models.py`)       | Dataform (`dataform/definitions/*.sqlx`) |
| Data-quality checks| `observability/checks.yaml`        | Dataform inline `assertions`           |
| Ingestion (scale)  | Python parquet writer              | Apache Beam / Dataflow (batch+stream)  |
| Reporting          | mart tables + `reports/*.md`       | Looker Studio on BigQuery              |
| Orchestration      | `make all` / GitHub Actions        | Cloud Composer (Airflow) / Workflows   |
| IaC                | —                                  | Terraform (planned)                    |

## Dataform assertions

`stg_events.sqlx` and `mart_campaign_efficiency.sqlx` carry inline assertions (`uniqueKey`,
`nonNull`, `rowConditions`). Dataform runs them alongside each model update and exposes the
failing rows — the managed equivalent of the local `dq_audit_results` audit table.

> Status: the DuckDB path is fully runnable today. The Dataform/Beam/Terraform pieces here are
> the scaffolding for the incremental GCP migration; see the roadmap in the root README.
