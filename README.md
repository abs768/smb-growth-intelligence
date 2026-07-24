# SMB Growth Intelligence Platform

**▶ [Live dashboard](https://abs768.github.io/smb-growth-intelligence/)** — rebuilt by running the pipeline end-to-end on a clean runner, so the numbers there are a real execution, not a committed snapshot.

[![platform-ci](https://github.com/abs768/smb-growth-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/abs768/smb-growth-intelligence/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

An end-to-end analytics-engineering platform that turns raw GA4 ecommerce events into tested,
decision-facing customer and campaign tables — and automates a purchase-propensity model on top.

It runs **fully locally today** on DuckDB (`make all`, ~4 seconds, zero setup, zero cloud cost)
and is built to port to **GCP-native infrastructure** (BigQuery + Dataform + Dataflow + Looker
Studio) without rewriting the modeling logic — see [`/bigquery`](bigquery/README.md).

> **Prototype status.** The DuckDB pipeline, feature framework, model automation, data-quality
> layer, tests and CI are complete and runnable. The GCP components (Dataform/Beam/Terraform)
> are scaffolded with real, reviewed SQL and a migration path — see [Roadmap](#roadmap). All
> metrics below are **measured on the local prototype** (synthetic GA4-shaped data, `seed=42`)
> and are reproduced on every run into [`reports/metrics.json`](reports/metrics.json).

## Why this exists

It demonstrates the full data-engineering loop on one coherent problem:

**ETL → feature engineering → model automation → data quality → reporting.**

| Requirement | Where it lives |
|---|---|
| Scalable ETL / data modeling | layered SQL: staging → intermediate → marts (`src/smb/pipeline`) |
| Feature engineering support | config-driven, point-in-time feature store (`src/smb/features`) |
| Model automation | backfill → walk-forward train → score back to warehouse (`train.py`) |
| Data quality & observability | YAML assertions → audit table → quality score (`src/smb/observability`) |
| Reporting | decision-facing marts + generated reports; Looker Studio on the GCP path |

## Measured results (local prototype, reproducible)

| Metric | Value |
|---|---|
| Events processed | **217,131** (from 219,122 raw) |
| Pipeline success rate | **100%** (10/10 models) |
| Model exec latency p50 / p95 | **~7 ms / ~0.4 s** |
| Bad records quarantined | **685 (0.31%)** — caught at ingestion, not silently loaded |
| Feature store | **9 features × 3 backfill cutoffs**, point-in-time; leakage check ✅ |
| Propensity model ROC-AUC vs baseline | **0.647 vs 0.602 (+0.044)** |
| Top-decile lift over base rate | **2.18×** |
| Data-quality assertions | **11/11 passed**, quality score **100/100** |
| End-to-end wall time | **~4 s** |

## Business questions the marts answer

| Question | Model |
|---|---|
| Which users are most likely to purchase? | `mart_customer_features` + `mart_propensity_scores` |
| Where are customers abandoning the funnel? | `mart_funnel` (stage-to-stage drop-off by source) |
| Which traffic sources drive high-value customers? | `mart_campaign_efficiency` (ROAS / CAC) |
| Which products are viewed but rarely purchased? | `mart_product_affinity` (showcase-underperformer flag) |
| Which cohorts retain best? | `mart_cohort_retention` |
| Who should get a remarketing campaign? | top-decile of `mart_propensity_scores` |

## Quickstart

```bash
make setup     # create .venv and install deps
make all       # generate -> ETL -> features -> train -> quality  (writes reports/)
```

Or step by step: `make generate`, `make pipeline`, `make features`, `make train`, `make quality`.
Run the invariant + data-quality tests with `pytest -q`.

## Feature framework (declarative)

A data scientist adds a block to [`features.yaml`](src/smb/features/features.yaml); the framework
generates point-in-time-correct SQL, backfills it across cutoffs, and attaches a forward label —
no pipeline code changes:

```yaml
- name: revenue_last_30d
  aggregation: sum
  column: purchase_revenue
  filter: "event_name = 'purchase'"
  window_days: 30
```

**Leakage safety:** features read only `event_timestamp <= as_of`; the label reads only the
window *after* `as_of`. A build-time assertion fails the run on any point-in-time violation.

## Data quality & observability

[`checks.yaml`](src/smb/observability/checks.yaml) declares row-count, freshness, null, uniqueness,
accepted-value, range, reconciliation, referential-integrity and quarantine-rate checks. Every
result is written to the append-only `dq_audit_results` audit table (so quality can be trended),
rolled into a severity-weighted score, and a **critical breach fails CI**. See
[`reports/data_quality.md`](reports/data_quality.md).

## Repo layout

```
src/smb/
  generate_data.py          GA4-shaped synthetic source data (GCS raw zone stand-in)
  pipeline/                 SQL runner + staging/intermediate/marts models
  features/                 features.yaml, point-in-time builder, model training
  observability/            checks.yaml + assertion engine + audit table
  run.py                    end-to-end orchestrator -> reports/metrics.json
bigquery/                   GCP path: BigQuery SQL + Dataform assertions + setup guide
docs/                       architecture (diagrams + DAG), data model
tests/                      pipeline invariants + data-quality gate
reports/                    committed evidence of the latest run
```

## GCP portability

The [`/bigquery`](bigquery/README.md) folder holds the real GCP-side equivalents: BigQuery SQL
that flattens Google's public `ga4_obfuscated_sample_ecommerce` export, Dataform models with
inline assertions, partition/cluster cost guardrails, and a local→GCP mapping table.

## Roadmap

- [x] Layered ETL (staging → intermediate → marts) on DuckDB, BigQuery-portable SQL
- [x] Config-driven, point-in-time feature store with backfill + leakage guard
- [x] Model automation: walk-forward training vs baseline, scores written back
- [x] Data-quality assertion engine + audit table + CI gate
- [x] BigQuery SQL + Dataform assertions for the GA4 public dataset
- [ ] Run the Dataform project against a live BigQuery sandbox; publish Looker Studio dashboards
- [ ] Apache Beam / Dataflow ingestion for the scalable batch+stream path
- [ ] Terraform for BigQuery datasets, Dataform, and scheduling (Cloud Composer)
- [ ] Incremental (append-only) feature and mart materializations

## Résumé framing

**Accurate today (prototype):** *Built an end-to-end SMB growth analytics platform — layered SQL
ETL, a config-driven point-in-time feature store, walk-forward propensity modeling, and a
YAML-driven data-quality engine with a CI gate — processing ~217K GA4-shaped events at 100%
pipeline reliability, 0.31% bad-record quarantine, and 2.18× top-decile model lift over baseline.*

**Target after GCP migration:** *…on GCP using Apache Beam/Dataflow, BigQuery, Dataform and Looker
Studio, with Terraform + GitHub Actions delivery.* Fill in production X/Y/Z only after measuring
them on the live GCP build.
