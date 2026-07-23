# Architecture

## Platform overview

```mermaid
flowchart LR
  subgraph SRC[Sources]
    GA4[GA4 ecommerce events]
    ADS[Ad spend]
    CRM[CRM customers]
  end

  subgraph RAW[Raw zone]
    P[(Parquet / GCS)]
  end

  subgraph WH[Warehouse]
    STG[staging]
    INT[intermediate]
    MART[marts]
  end

  subgraph ML[Feature + model automation]
    FS[(feature_store<br/>point-in-time, backfilled)]
    MODEL[propensity model<br/>vs baseline]
    SCORES[(mart_propensity_scores)]
  end

  subgraph OBS[Observability]
    DQ[assertions]
    AUDIT[(dq_audit_results)]
  end

  RPT[Looker Studio /<br/>reports]

  GA4 & ADS & CRM --> P --> STG --> INT --> MART
  MART --> RPT
  STG --> FS --> MODEL --> SCORES --> RPT
  STG & INT & MART --> DQ --> AUDIT --> RPT
```

- **Local prototype:** raw = Parquet, warehouse = DuckDB, transforms = a small SQL runner,
  checks = a YAML-driven assertion engine, model = scikit-learn.
- **GCP build:** raw = Cloud Storage + GA4 public dataset, warehouse = BigQuery, transforms +
  assertions = Dataform, ingestion at scale = Apache Beam / Dataflow, reporting = Looker Studio.
  See [`/bigquery`](../bigquery/README.md).

## Pipeline DAG (model dependencies)

```mermaid
flowchart TD
  raw_events[/data/raw/events/] --> stg_events
  raw_events --> stg_events_rejected
  raw_ad_spend[/data/raw/ad_spend/] --> stg_ad_spend
  raw_crm[/data/raw/crm_customers/] --> stg_crm_customers

  stg_events --> int_sessions
  int_sessions --> mart_customer_features
  int_sessions --> mart_funnel
  int_sessions --> mart_cohort_retention
  int_sessions --> mart_campaign_efficiency
  stg_ad_spend --> mart_campaign_efficiency
  stg_crm_customers --> mart_cohort_retention
  stg_events --> mart_product_affinity

  stg_events --> feature_store
  feature_store --> propensity_model --> mart_propensity_scores
```

## Point-in-time correctness (no leakage)

Every feature is computed only from events with `event_timestamp <= as_of_date`; the label is
computed only from events in `(as_of_date, as_of_date + horizon]`. The feature store is backfilled
across multiple `as_of` cutoffs, and the model is evaluated **walk-forward** (train on earlier
cutoffs, validate on the most recent). A build-time assertion fails the run if any feature row
implies future data leaked in.
