"""Pipeline invariants + data-quality gate. Runs the whole platform once, then asserts the
properties a reviewer (or a scheduled production run) should be able to rely on.
"""
import os

import duckdb
import pytest

from smb import config
from smb import generate_data
from smb.pipeline import run_models
from smb.features import build_features, train
from smb.observability import run_checks


@pytest.fixture(scope="module")
def platform():
    if not os.path.exists(config.RAW_EVENTS):
        generate_data.write_parquet(generate_data.generate(42))
    pipe = run_models.run(verbose=False)
    feat = build_features.build(verbose=False)
    model = train.train(verbose=False)
    dq, crit = run_checks.run(verbose=False)
    return dict(pipe=pipe, feat=feat, model=model, dq=dq, crit=crit)


def test_all_models_succeed(platform):
    assert platform["pipe"]["pipeline_success_rate"] == 1.0


def test_events_processed_reasonable(platform):
    assert platform["pipe"]["events_processed"] > 150_000


def test_bad_records_are_quarantined(platform):
    # the generator injects dirty rows; they must be caught, not silently loaded
    assert platform["pipe"]["records_quarantined"] > 0
    assert platform["pipe"]["quarantine_rate"] < 0.02


def test_no_training_serving_leakage(platform):
    assert platform["feat"]["leakage_check_passed"] is True
    con = duckdb.connect(config.WAREHOUSE)
    negatives = con.execute(
        "SELECT count(*) FROM feature_store WHERE days_since_last_event < 0"
    ).fetchone()[0]
    con.close()
    assert negatives == 0


def test_model_beats_baseline(platform):
    assert platform["model"]["roc_auc_improvement_vs_baseline"] > 0
    assert platform["model"]["model"]["top_decile_lift"] > 1.5


def test_data_quality_gate(platform):
    assert platform["dq"]["critical_failures"] == 0
    assert platform["dq"]["quality_score"] >= 90
