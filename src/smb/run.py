"""End-to-end orchestrator: generate -> pipeline -> features -> train -> quality.

Runs the whole platform, times each phase, and writes a single consolidated reports/metrics.json
that the README's metrics table is populated from. This is what CI executes on every push.
"""
from __future__ import annotations

import argparse
import json
import os
import time

from smb import config


def _phase(name, fn):
    print(f"\n=== {name} ===")
    t0 = time.perf_counter()
    out = fn()
    dt = time.perf_counter() - t0
    print(f"  ({name} took {dt:.2f}s)")
    return out, round(dt, 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-generate", action="store_true", help="reuse existing raw data")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    from smb import generate_data
    from smb.pipeline import run_models
    from smb.features import build_features, train
    from smb.observability import run_checks

    timings = {}

    if not (args.skip_generate and os.path.exists(config.RAW_EVENTS)):
        _, timings["generate"] = _phase("1/5 generate raw data", lambda: generate_data.write_parquet(
            generate_data.generate(args.seed)))

    pipe, timings["pipeline"] = _phase("2/5 run ETL pipeline", lambda: run_models.run())
    feat, timings["features"] = _phase("3/5 build feature store", lambda: build_features.build())
    model, timings["train"] = _phase("4/5 train propensity model", lambda: train.train())
    (dq, crit), timings["quality"] = _phase("5/5 data-quality checks", lambda: run_checks.run())

    metrics = {
        "pipeline": {
            "events_processed": pipe["events_processed"],
            "raw_events": pipe["raw_events"],
            "models_run": pipe["models_run"],
            "pipeline_success_rate": pipe["pipeline_success_rate"],
            "model_latency_p50_s": pipe["model_latency_p50_s"],
            "model_latency_p95_s": pipe["model_latency_p95_s"],
            "records_quarantined": pipe["records_quarantined"],
            "quarantine_rate": pipe["quarantine_rate"],
        },
        "features": {
            "n_features": feat["n_features"],
            "feature_store_rows": feat["feature_store_rows"],
            "backfill_cutoffs": len(feat["cutoffs"]),
            "leakage_check_passed": feat["leakage_check_passed"],
        },
        "model": {
            "roc_auc": model["model"]["roc_auc"],
            "baseline_roc_auc": model["baseline_add_to_cart"]["roc_auc"],
            "roc_auc_improvement_vs_baseline": model["roc_auc_improvement_vs_baseline"],
            "top_decile_lift": model["model"]["top_decile_lift"],
        },
        "quality": {
            "assertions": dq["checks_total"],
            "assertions_passed": dq["checks_passed"],
            "quality_score": dq["quality_score"],
            "critical_failures": dq["critical_failures"],
        },
        "phase_timings_s": timings,
        "total_pipeline_seconds": round(sum(timings.values()), 2),
    }
    with open(os.path.join(config.REPORTS_DIR, "metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    p, m, q = metrics["pipeline"], metrics["model"], metrics["quality"]
    print("\n" + "=" * 64)
    print("PLATFORM RUN SUMMARY")
    print("=" * 64)
    print(f"  events processed        : {p['events_processed']:,}")
    print(f"  pipeline success rate   : {p['pipeline_success_rate']*100:.0f}%")
    print(f"  model latency p50 / p95 : {p['model_latency_p50_s']*1000:.0f} / {p['model_latency_p95_s']*1000:.0f} ms")
    print(f"  records quarantined     : {p['records_quarantined']:,} ({p['quarantine_rate']*100:.2f}%)")
    print(f"  features / cutoffs      : {metrics['features']['n_features']} features x {metrics['features']['backfill_cutoffs']} backfill cutoffs")
    print(f"  model ROC-AUC vs base   : {m['roc_auc']:.3f} vs {m['baseline_roc_auc']:.3f} (+{m['roc_auc_improvement_vs_baseline']:.3f})")
    print(f"  top-decile lift         : {m['top_decile_lift']:.2f}x")
    print(f"  DQ assertions / score   : {q['assertions_passed']}/{q['assertions']} passed | {q['quality_score']}/100")
    print(f"  total wall time         : {metrics['total_pipeline_seconds']}s")
    print("=" * 64)
    return 1 if crit else 0


if __name__ == "__main__":
    raise SystemExit(main())
