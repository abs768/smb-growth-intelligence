"""Model automation: train a purchase-propensity model on the backfilled feature store,
evaluate it walk-forward against a baseline, and write scores back to the warehouse.

Walk-forward: train on the earlier cutoffs, validate on the most recent one (so we never
evaluate on data from a period the model was trained on). Every model is compared to a
simple, explainable baseline -- a model that can't beat the baseline isn't worth shipping.

Outputs:
  * warehouse table `mart_propensity_scores` -- who to target for remarketing.
  * reports/model_metrics.json -- AUC / PR-AUC / top-decile lift vs baseline.
"""
from __future__ import annotations

import json
import os

import duckdb
import numpy as np
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from smb import config
from smb.features.build_features import FEATURES_YAML

with open(FEATURES_YAML) as _fh:
    LABEL = yaml.safe_load(_fh)["label"]["name"]


def _decile_lift(y_true: np.ndarray, scores: np.ndarray, frac: float = 0.10) -> float:
    """Positive rate in the top `frac` by score, divided by the overall positive rate."""
    base = y_true.mean()
    if base == 0:
        return 0.0
    k = max(1, int(len(scores) * frac))
    top = np.argsort(scores)[::-1][:k]
    return float(y_true[top].mean() / base)


def train(verbose: bool = True) -> dict:
    con = duckdb.connect(config.WAREHOUSE)
    df = con.execute("SELECT * FROM feature_store").fetch_df()

    feature_cols = [c for c in df.columns if c not in ("entity_id", "as_of_date", LABEL)]
    cutoffs = sorted(df["as_of_date"].astype(str).unique())
    train_cutoffs, valid_cutoff = cutoffs[:-1], cutoffs[-1]

    tr = df[df["as_of_date"].astype(str).isin(train_cutoffs)]
    va = df[df["as_of_date"].astype(str) == valid_cutoff]

    Xtr, ytr = tr[feature_cols].to_numpy(), tr[LABEL].to_numpy()
    Xva, yva = va[feature_cols].to_numpy(), va[LABEL].to_numpy()

    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=1000, class_weight="balanced"),
    )
    model.fit(Xtr, ytr)
    proba = model.predict_proba(Xva)[:, 1]

    # Baseline: rank users by a single obvious signal (recent add-to-cart count).
    baseline_score = va["add_to_cart_last_14d"].to_numpy().astype(float)

    metrics = {
        "train_cutoffs": train_cutoffs,
        "valid_cutoff": valid_cutoff,
        "n_train": int(len(tr)),
        "n_valid": int(len(va)),
        "valid_base_rate": round(float(yva.mean()), 4),
        "model": {
            "roc_auc": round(float(roc_auc_score(yva, proba)), 4),
            "pr_auc": round(float(average_precision_score(yva, proba)), 4),
            "top_decile_lift": round(_decile_lift(yva, proba), 3),
        },
        "baseline_add_to_cart": {
            "roc_auc": round(float(roc_auc_score(yva, baseline_score)), 4),
            "pr_auc": round(float(average_precision_score(yva, baseline_score)), 4),
            "top_decile_lift": round(_decile_lift(yva, baseline_score), 3),
        },
    }
    metrics["roc_auc_improvement_vs_baseline"] = round(
        metrics["model"]["roc_auc"] - metrics["baseline_add_to_cart"]["roc_auc"], 4
    )
    # Feature importance (standardized logistic coefficients).
    coefs = model.named_steps["logisticregression"].coef_[0]
    metrics["feature_importance"] = dict(
        sorted(
            ((c, round(float(w), 4)) for c, w in zip(feature_cols, coefs)),
            key=lambda kv: abs(kv[1]),
            reverse=True,
        )
    )

    # ---- write propensity scores for the validation cutoff back to the warehouse ----
    scores_df = va[["entity_id"]].copy()
    scores_df["as_of_date"] = valid_cutoff
    scores_df["propensity"] = proba
    scores_df["decile"] = (scores_df["propensity"].rank(pct=True) * 10).clip(upper=10).astype(int)
    scores_df["actual_label"] = yva
    con.register("scores_df", scores_df)
    con.execute("CREATE OR REPLACE TABLE mart_propensity_scores AS SELECT * FROM scores_df")
    con.unregister("scores_df")
    con.close()

    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    with open(os.path.join(config.REPORTS_DIR, "model_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2)

    if verbose:
        m, b = metrics["model"], metrics["baseline_add_to_cart"]
        print(f"  walk-forward: train {train_cutoffs} -> validate {valid_cutoff}")
        print(f"  model    ROC-AUC {m['roc_auc']:.3f} | PR-AUC {m['pr_auc']:.3f} | "
              f"top-decile lift {m['top_decile_lift']:.2f}x")
        print(f"  baseline ROC-AUC {b['roc_auc']:.3f} | PR-AUC {b['pr_auc']:.3f} | "
              f"top-decile lift {b['top_decile_lift']:.2f}x")
        print(f"  improvement over baseline: +{metrics['roc_auc_improvement_vs_baseline']:.3f} ROC-AUC")
    return metrics


if __name__ == "__main__":
    train()
