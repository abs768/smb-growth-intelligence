# Data model

Layered warehouse: **staging** (clean & typed) → **intermediate** (sessionized) → **marts**
(decision-facing). Feature and observability tables are built on top.

## Staging

| Model | Grain | Notes |
|---|---|---|
| `stg_events` | one row per event | typed, deduplicated on `event_id`, invalid rows removed |
| `stg_events_rejected` | one row per bad event | quarantine zone with `reject_reason` |
| `stg_ad_spend` | campaign × day | advertising cost / impressions / clicks |
| `stg_crm_customers` | one row per customer | signup date, plan, region |

## Intermediate

| Model | Grain | Key columns |
|---|---|---|
| `int_sessions` | one row per GA session | funnel flags (`did_view`, `did_add_to_cart`, `did_checkout`, `did_purchase`), `revenue` |

## Marts

| Model | Grain | Answers |
|---|---|---|
| `mart_customer_features` | customer | recency / frequency / monetary, AOV, conversion rate, funnel abandonment — *who is likely to buy?* |
| `mart_funnel` | traffic source | stage-to-stage drop-off — *where do customers abandon?* |
| `mart_campaign_efficiency` | campaign | spend, CAC, ROAS, conversion — *which sources drive value?* |
| `mart_product_affinity` | product | view-to-purchase rate, showcase-underperformer flag — *viewed but not bought?* |
| `mart_cohort_retention` | signup week × weeks-since | retention curves — *which cohorts retain?* |
| `mart_propensity_scores` | customer | model score + decile — *who to remarket to?* |

## Feature / ML

| Table | Grain | Notes |
|---|---|---|
| `feature_store` | entity × `as_of_date` | 9 point-in-time features, backfilled across cutoffs, with forward label |
| `mart_propensity_scores` | entity | validation-cutoff propensity + decile + actual label |

## Observability

| Table | Grain | Notes |
|---|---|---|
| `dq_audit_results` | check × run | append-only history: status, observed, threshold, severity — trend quality over time |
