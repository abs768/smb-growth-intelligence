"""Minimal dbt-style SQL runner for the local DuckDB warehouse.

Executes every model under src/smb/pipeline/models/<layer>/*.sql in layer order
(staging -> intermediate -> marts), materializing each as a table in the warehouse.
Captures per-model runtime and row counts so the pipeline can publish *real*
latency and reliability metrics (no hand-waving).

The identical transformation logic ships as BigQuery SQL / Dataform under /bigquery
for the GCP build.
"""
from __future__ import annotations

import glob
import json
import os
import time

import duckdb

from smb import config


def _models_in(layer: str) -> list[str]:
    path = os.path.join(config.MODELS_DIR, layer, "*.sql")
    return sorted(glob.glob(path))


def run(verbose: bool = True) -> dict:
    # Fresh warehouse each run == reproducible, deterministic pipeline.
    if os.path.exists(config.WAREHOUSE):
        os.remove(config.WAREHOUSE)
    con = duckdb.connect(config.WAREHOUSE)

    results = []
    for layer in config.LAYERS:
        for sql_path in _models_in(layer):
            model = os.path.splitext(os.path.basename(sql_path))[0]
            with open(sql_path) as fh:
                sql = fh.read()
            t0 = time.perf_counter()
            status, rows, err = "success", 0, None
            try:
                con.execute(f"CREATE OR REPLACE TABLE {model} AS ({sql})")
                rows = con.execute(f"SELECT count(*) FROM {model}").fetchone()[0]
            except Exception as exc:  # noqa: BLE001 - we want to record, not crash the run
                status, err = "failed", str(exc).splitlines()[0]
            dt = time.perf_counter() - t0
            results.append(
                dict(model=model, layer=layer, rows=rows, seconds=round(dt, 4), status=status, error=err)
            )
            if verbose:
                mark = "ok " if status == "success" else "ERR"
                print(f"  [{mark}] {layer:12s} {model:26s} {rows:>8,} rows  {dt*1000:7.1f} ms"
                      + (f"  <- {err}" if err else ""))

    # ---- pipeline-level metrics ----
    durations = sorted(r["seconds"] for r in results)
    n = len(durations)
    ok = sum(1 for r in results if r["status"] == "success")

    def pct(p):
        if not durations:
            return 0.0
        return round(durations[min(n - 1, int(p * n))], 4)

    raw_total = con.execute(
        "SELECT count(*) FROM read_parquet('data/raw/events/events.parquet')"
    ).fetchone()[0]
    quarantined = _rows(con, "stg_events_rejected")
    clean = _rows(con, "stg_events")

    metrics = {
        "models_run": n,
        "models_succeeded": ok,
        "pipeline_success_rate": round(ok / n, 4) if n else 0.0,
        "total_wall_seconds": round(sum(r["seconds"] for r in results), 4),
        "model_latency_p50_s": pct(0.50),
        "model_latency_p95_s": pct(0.95),
        "raw_events": raw_total,
        "events_processed": clean,
        "records_quarantined": quarantined,
        "quarantine_rate": round(quarantined / raw_total, 5) if raw_total else 0.0,
        "dedup_removed": max(0, raw_total - quarantined - clean),
        "models": results,
    }

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    with open(os.path.join(config.REPORTS_DIR, "pipeline_run.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)
    con.close()

    if verbose:
        print(f"\n  {ok}/{n} models succeeded | {clean:,} events processed | "
              f"{quarantined:,} quarantined ({metrics['quarantine_rate']*100:.2f}%) | "
              f"p95 model latency {metrics['model_latency_p95_s']*1000:.0f} ms")
    return metrics


def _rows(con, table) -> int:
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    except Exception:
        return 0


if __name__ == "__main__":
    run()
