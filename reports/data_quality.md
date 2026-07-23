# Data Quality Report

- **Quality score:** 100.0/100
- **Checks:** 11/11 passed (0 critical failures)
- **Run:** 2026-07-23T18:20:30.603667+00:00

| Check | Severity | Status | Observed | Threshold |
|---|---|---|---|---|
| events_volume | critical | pass | 2.171e+05 | 1e+05 |
| events_freshness | critical | pass | 0 | 2 |
| user_id_not_null | critical | pass | 0 | 0 |
| event_id_unique | critical | pass | 0 | 0 |
| event_name_accepted | high | pass | 0 | 0 |
| revenue_non_negative | high | pass | 12.7 | 0 |
| sessions_reconcile_events | high | pass | 3.641e+04 | 3.641e+04 |
| customer_features_unique | high | pass | 0 | 0 |
| conversion_rate_plausible | medium | pass | 0.0763 | 0.2 |
| propensity_scores_not_orphaned | medium | pass | 0 | 0 |
| quarantine_rate_within_slo | medium | pass | 0.003126 | 0.02 |
