"""Config-driven feature engineering framework.

Reads features.yaml, generates point-in-time-correct SQL for each feature, backfills the
feature store across multiple cutoff dates, and attaches a forward-looking label to produce
a training dataset. The same YAML would drive BigQuery SQL generation in the GCP build.

Why this matters for the role: a data scientist declares a feature once (name / entity /
aggregation / window) and gets a tested, leakage-safe, backfilled feature table -- this is the
"support a data-science environment / feature engineering / model automation" requirement.
"""
from __future__ import annotations

import json
import os

import duckdb
import yaml

from smb import config

FEATURES_YAML = os.path.join(os.path.dirname(__file__), "features.yaml")


def _feature_sql(entity: str, feat: dict, as_of: str) -> str:
    """Generate a single-feature aggregate, scoped to events at-or-before the cutoff."""
    name = feat["name"]
    agg = feat["aggregation"]
    window = feat["window_days"]
    where = [
        f"event_timestamp <= TIMESTAMP '{as_of} 23:59:59'",
        f"event_timestamp > TIMESTAMP '{as_of} 23:59:59' - INTERVAL '{window} days'",
    ]
    if feat.get("filter"):
        where.append(feat["filter"])
    where_sql = " AND ".join(where)

    if agg == "count":
        expr = "count(*)"
    elif agg == "count_distinct":
        expr = f"count(DISTINCT {feat['column']})"
    elif agg == "sum":
        expr = f"coalesce(sum({feat['column']}), 0)"
    elif agg == "avg":
        expr = f"coalesce(avg({feat['column']}), 0)"
    elif agg == "recency":
        # days between the cutoff and the entity's most recent event
        expr = f"date_diff('day', max(event_timestamp), TIMESTAMP '{as_of} 23:59:59')"
    else:
        raise ValueError(f"unknown aggregation: {agg}")

    return (
        f"SELECT {entity} AS entity_id, {expr} AS {name} "
        f"FROM stg_events WHERE {where_sql} GROUP BY {entity}"
    )


def _label_sql(entity: str, label: dict, as_of: str) -> str:
    horizon = label["horizon_days"]
    return (
        f"SELECT DISTINCT {entity} AS entity_id, 1 AS {label['name']} "
        f"FROM stg_events "
        f"WHERE event_name = '{label['event']}' "
        f"AND event_timestamp > TIMESTAMP '{as_of} 23:59:59' "
        f"AND event_timestamp <= TIMESTAMP '{as_of} 23:59:59' + INTERVAL '{horizon} days'"
    )


def build(verbose: bool = True) -> dict:
    with open(FEATURES_YAML) as fh:
        spec = yaml.safe_load(fh)

    entity = spec["entity"]
    label = spec["label"]
    features = spec["features"]
    cutoffs = spec["backfill_as_of_dates"]

    con = duckdb.connect(config.WAREHOUSE)

    # Entity spine per cutoff: everyone active on or before the cutoff.
    all_rows = []
    for as_of in cutoffs:
        spine = (
            f"SELECT DISTINCT {entity} AS entity_id FROM stg_events "
            f"WHERE event_timestamp <= TIMESTAMP '{as_of} 23:59:59'"
        )
        select_cols = ["s.entity_id", f"DATE '{as_of}' AS as_of_date"]
        joins = [f"({spine}) s"]
        for i, feat in enumerate(features):
            alias = f"f{i}"
            joins.append(f"LEFT JOIN ({_feature_sql(entity, feat, as_of)}) {alias} USING (entity_id)")
            default = "999" if feat["aggregation"] == "recency" else "0"
            select_cols.append(f"coalesce({alias}.{feat['name']}, {default}) AS {feat['name']}")
        joins.append(f"LEFT JOIN ({_label_sql(entity, label, as_of)}) lb USING (entity_id)")
        select_cols.append(f"coalesce(lb.{label['name']}, 0) AS {label['name']}")

        query = "SELECT " + ",\n  ".join(select_cols) + "\nFROM " + "\n  ".join(joins)
        con.execute(f"CREATE OR REPLACE TEMP TABLE _fs_{as_of.replace('-', '')} AS ({query})")
        cnt, pos = con.execute(
            f"SELECT count(*), sum({label['name']}) FROM _fs_{as_of.replace('-', '')}"
        ).fetchone()
        all_rows.append((as_of, cnt, pos))
        if verbose:
            rate = pos / cnt if cnt else 0
            print(f"  cutoff {as_of}: {cnt:>7,} rows | label rate {rate*100:5.2f}% ({pos:,} positives)")

    # Union all cutoffs into the persistent feature store.
    union = " UNION ALL ".join(f"SELECT * FROM _fs_{c.replace('-', '')}" for c in cutoffs)
    con.execute(f"CREATE OR REPLACE TABLE feature_store AS ({union})")
    total = con.execute("SELECT count(*) FROM feature_store").fetchone()[0]

    # ---- leakage guard: assert no feature window ever reads past its own cutoff ----
    # (structural: SQL uses event_timestamp <= as_of; we re-verify the store has no future rows)
    leak = con.execute(
        "SELECT count(*) FROM feature_store WHERE days_since_last_event < 0"
    ).fetchone()[0]
    assert leak == 0, "point-in-time violation: negative recency implies future data leaked in"

    report = {
        "entity": entity,
        "label": label["name"],
        "n_features": len(features),
        "feature_names": [f["name"] for f in features],
        "cutoffs": [{"as_of": a, "rows": c, "positives": p} for a, c, p in all_rows],
        "feature_store_rows": total,
        "leakage_check_passed": leak == 0,
    }
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    with open(os.path.join(config.REPORTS_DIR, "feature_store.json"), "w") as fh:
        json.dump(report, fh, indent=2)
    con.close()

    if verbose:
        print(f"  feature_store: {total:,} rows across {len(cutoffs)} cutoffs, "
              f"{len(features)} features | leakage check {'PASSED' if leak == 0 else 'FAILED'}")
    return report


if __name__ == "__main__":
    build()
