"""Reusable data-quality / observability framework.

Runs the declarative checks in checks.yaml against the warehouse, writes every result to a
persistent `dq_audit_results` audit table (so quality can be trended over time), and rolls
the results up into a single quality score. Fails the process on a critical breach so CI
blocks a bad pipeline.

Check types: row_count_min, freshness, not_null, unique, accepted_values, min_value,
range_agg, reconcile_count, relationship, quarantine_rate.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

import duckdb
import yaml

from smb import config

CHECKS_YAML = os.path.join(os.path.dirname(__file__), "checks.yaml")
SEVERITY_WEIGHT = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _result(check, status, observed, threshold):
    return dict(
        check_name=check["name"],
        check_type=check["type"],
        table_name=check.get("table") or check.get("rejected_table"),
        column_name=check.get("column"),
        severity=check.get("severity", "medium"),
        status=status,
        observed=None if observed is None else float(observed),
        threshold=None if threshold is None else float(threshold),
    )


def _run_check(con, check, reference_date):
    t = check["type"]
    tbl = check.get("table")
    col = check.get("column")

    if t == "row_count_min":
        n = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        return _result(check, "pass" if n >= check["min"] else "fail", n, check["min"])

    if t == "freshness":
        newest = con.execute(f"SELECT max({col}) FROM {tbl}").fetchone()[0]
        ref = datetime.fromisoformat(reference_date).date()
        days = (ref - newest).days
        return _result(check, "pass" if days <= check["max_days"] else "fail", days, check["max_days"])

    if t == "not_null":
        rate = con.execute(
            f"SELECT coalesce(sum(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END)::DOUBLE/nullif(count(*),0),0) FROM {tbl}"
        ).fetchone()[0]
        return _result(check, "pass" if rate <= check["max_null_rate"] else "fail", rate, check["max_null_rate"])

    if t == "unique":
        dupes = con.execute(
            f"SELECT count(*) FROM (SELECT {col} FROM {tbl} GROUP BY {col} HAVING count(*) > 1)"
        ).fetchone()[0]
        return _result(check, "pass" if dupes == 0 else "fail", dupes, 0)

    if t == "accepted_values":
        allowed = ", ".join(f"'{v}'" for v in check["values"])
        bad = con.execute(
            f"SELECT count(*) FROM {tbl} WHERE {col} NOT IN ({allowed})"
        ).fetchone()[0]
        return _result(check, "pass" if bad == 0 else "fail", bad, 0)

    if t == "min_value":
        mn = con.execute(f"SELECT min({col}) FROM {tbl}").fetchone()[0]
        return _result(check, "pass" if mn is None or mn >= check["min"] else "fail", mn, check["min"])

    if t == "range_agg":
        val = con.execute(f"SELECT {check['expr']} FROM {tbl}").fetchone()[0]
        ok = val is not None and check["min"] <= val <= check["max"]
        return _result(check, "pass" if ok else "fail", val, check["max"])

    if t == "reconcile_count":
        target = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        source = con.execute(f"SELECT {check['source_expr']} FROM {check['source_table']}").fetchone()[0]
        return _result(check, "pass" if target == source else "fail", target, source)

    if t == "relationship":
        orphans = con.execute(
            f"SELECT count(*) FROM {tbl} a "
            f"LEFT JOIN {check['to_table']} b ON a.{col} = b.{check['to_column']} "
            f"WHERE b.{check['to_column']} IS NULL"
        ).fetchone()[0]
        return _result(check, "pass" if orphans == 0 else "fail", orphans, 0)

    if t == "quarantine_rate":
        rej = con.execute(f"SELECT count(*) FROM {check['rejected_table']}").fetchone()[0]
        raw = con.execute(f"SELECT count(*) FROM read_parquet('{check['raw_glob']}')").fetchone()[0]
        rate = rej / raw if raw else 0
        return _result(check, "pass" if rate <= check["max_rate"] else "fail", rate, check["max_rate"])

    raise ValueError(f"unknown check type: {t}")


def run(verbose: bool = True) -> dict:
    with open(CHECKS_YAML) as fh:
        spec = yaml.safe_load(fh)

    con = duckdb.connect(config.WAREHOUSE)
    run_ts = datetime.now(timezone.utc).isoformat()
    rows = []
    for check in spec["checks"]:
        try:
            r = _run_check(con, check, spec["reference_date"])
        except Exception as exc:  # noqa: BLE001
            r = _result(check, "error", None, None)
            r["error"] = str(exc).splitlines()[0]
        r["run_ts"] = run_ts
        rows.append(r)
        if verbose:
            icon = {"pass": "PASS", "fail": "FAIL", "error": "ERR "}[r["status"]]
            obs = "" if r["observed"] is None else f"observed={r['observed']:.4g}"
            print(f"  [{icon}] {r['severity']:8s} {r['check_name']:32s} {obs}")

    # persist to audit table (append-only history)
    con.register("rows_df", _to_df(rows))
    con.execute("CREATE TABLE IF NOT EXISTS dq_audit_results AS SELECT * FROM rows_df WHERE 1=0")
    con.execute("INSERT INTO dq_audit_results SELECT * FROM rows_df")
    con.unregister("rows_df")

    # quality score: severity-weighted pass rate
    wsum = sum(SEVERITY_WEIGHT[r["severity"]] for r in rows)
    wpass = sum(SEVERITY_WEIGHT[r["severity"]] for r in rows if r["status"] == "pass")
    score = round(100 * wpass / wsum, 1) if wsum else 0.0
    n_fail = sum(1 for r in rows if r["status"] != "pass")
    crit_fail = sum(1 for r in rows if r["severity"] == "critical" and r["status"] != "pass")

    summary = {
        "run_ts": run_ts,
        "checks_total": len(rows),
        "checks_passed": len(rows) - n_fail,
        "checks_failed": n_fail,
        "critical_failures": crit_fail,
        "quality_score": score,
        "results": rows,
    }
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    with open(os.path.join(config.REPORTS_DIR, "data_quality.json"), "w") as fh:
        json.dump(summary, fh, indent=2)
    _write_markdown(summary)
    con.close()

    if verbose:
        print(f"\n  quality score {score}/100 | {summary['checks_passed']}/{len(rows)} passed | "
              f"{crit_fail} critical failures")
    return summary, crit_fail


def _to_df(rows):
    import pandas as pd
    cols = ["run_ts", "check_name", "check_type", "table_name", "column_name",
            "severity", "status", "observed", "threshold"]
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows])


def _write_markdown(summary):
    lines = [
        "# Data Quality Report",
        "",
        f"- **Quality score:** {summary['quality_score']}/100",
        f"- **Checks:** {summary['checks_passed']}/{summary['checks_total']} passed "
        f"({summary['critical_failures']} critical failures)",
        f"- **Run:** {summary['run_ts']}",
        "",
        "| Check | Severity | Status | Observed | Threshold |",
        "|---|---|---|---|---|",
    ]
    for r in summary["results"]:
        obs = "" if r["observed"] is None else f"{r['observed']:.4g}"
        thr = "" if r["threshold"] is None else f"{r['threshold']:.4g}"
        lines.append(f"| {r['check_name']} | {r['severity']} | {r['status']} | {obs} | {thr} |")
    with open(os.path.join(config.REPORTS_DIR, "data_quality.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    _summary, crit = run()
    # Non-zero exit on a critical breach so CI fails loudly.
    sys.exit(1 if crit else 0)
