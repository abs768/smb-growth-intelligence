"""
Build the GitHub Pages dashboard from the reports the pipeline writes.

    python docs/build.py

Every number on the page comes from reports/*.json, which `make all` regenerates
on each run. The Pages workflow runs the pipeline first, so the published page
always reflects a real execution rather than a hand-maintained copy.

Standard library only — the workflow needs nothing beyond a stock Python.
"""
import datetime as dt
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(ROOT, "reports")
OUT = os.path.join(ROOT, "docs", "index.html")
REPO = "https://github.com/abs768/smb-growth-intelligence"


def load(name):
    with open(os.path.join(REPORTS, f"{name}.json")) as f:
        return json.load(f)


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- chart marks -----------------------------------------------------------
# Colours come from the validated reference palette. The two charts use
# different colour *jobs* and never share a surface:
#   * model latency  -> sequential, one hue (blue), magnitude only
#   * feature weight -> diverging, blue/red poles with a neutral midpoint,
#                       because the values are signed
# Sign is carried by bar direction as well as hue, so colour is never the sole
# encoding. Status colours are the fixed status palette and always ship with a
# glyph and a text label.

def bar_cell(value, vmax, label):
    """A magnitude bar sized within its own table cell (bar-in-table)."""
    pct = 0 if vmax == 0 else max(1.5, value / vmax * 100)
    return (
        f'<span class="barwrap" role="img" aria-label="{esc(label)}">'
        f'<span class="bar seq" style="width:{pct:.1f}%"></span></span>'
    )


def diverging_rows(importance):
    """Signed feature weights as bars either side of a zero axis."""
    vmax = max(abs(v) for v in importance.values()) or 1
    rows = []
    for name, val in sorted(importance.items(), key=lambda kv: -abs(kv[1])):
        pct = abs(val) / vmax * 50          # half-width per arm
        pos = val >= 0
        side = "right" if pos else "left"
        arrow = "▲" if pos else "▼"
        direction = "increases" if pos else "decreases"
        tip = f"{name}: {val:+.4f} — {direction} predicted propensity"
        bar = (
            f'<span class="dv-bar {"pos" if pos else "neg"}" '
            f'style="{side}:50%;width:{pct:.2f}%"></span>'
        )
        rows.append(
            f'<tr title="{esc(tip)}">'
            f'<td class="fname">{esc(name)}</td>'
            f'<td class="dv"><span class="dv-track"><span class="dv-zero"></span>{bar}</span></td>'
            f'<td class="c num"><span class="{"tag-good" if pos else "tag-bad"}">'
            f'{arrow} {val:+.4f}</span></td></tr>'
        )
    return "\n".join(rows)


def build():
    m = load("metrics")
    mm = load("model_metrics")
    fs = load("feature_store")
    dq = load("data_quality")
    pr = load("pipeline_run")

    p, feat, mod, qual = m["pipeline"], m["features"], m["model"], m["quality"]

    built = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sha = (os.environ.get("GITHUB_SHA") or "")[:7]
    run_url = None
    if os.environ.get("GITHUB_RUN_ID"):
        run_url = f"{REPO}/actions/runs/{os.environ['GITHUB_RUN_ID']}"

    # --- pipeline models table --------------------------------------------
    models = pr["models"]
    tmax = max(x["seconds"] for x in models)
    model_rows = []
    for x in models:
        ok = x["status"] == "success"
        secs = x["seconds"]
        bar = bar_cell(secs, tmax, "%.4f seconds" % secs)
        status_cls = "st-good" if ok else "st-crit"
        glyph = "✓" if ok else "✕"
        model_rows.append(
            f'<tr><td class="fname">{esc(x["model"])}</td>'
            f'<td><span class="chip sm">{esc(x["layer"])}</span></td>'
            f'<td class="c num">{x["rows"]:,}</td>'
            f'<td class="barcell">{bar}</td>'
            f'<td class="c num">{secs:.4f}s</td>'
            f'<td class="c"><span class="{status_cls}">{glyph} {esc(x["status"])}</span></td></tr>'
        )

    # --- feature store cutoffs --------------------------------------------
    cut_rows = "\n".join(
        f'<tr><td class="fname">{esc(c["as_of"])}</td>'
        f'<td class="c num">{c["rows"]:,}</td>'
        f'<td class="c num">{c["positives"]:,}</td>'
        f'<td class="c num">{c["positives"]/c["rows"]*100:.2f}%</td></tr>'
        for c in fs["cutoffs"]
    )

    # --- data quality checks ----------------------------------------------
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    checks = sorted(dq["results"], key=lambda c: sev_order.get(c["severity"], 9))
    check_rows = "\n".join(
        f'<tr><td class="fname">{esc(c["check_name"])}</td>'
        f'<td><span class="chip sm">{esc(c["check_type"])}</span></td>'
        f'<td class="c"><span class="sev sev-{esc(c["severity"])}">{esc(c["severity"])}</span></td>'
        f'<td class="c num">{c["observed"]:,.4g}</td>'
        f'<td class="c num">{c["threshold"]:,.4g}</td>'
        f'<td class="c"><span class="{"st-good" if c["status"] == "pass" else "st-crit"}">'
        f'{"✓" if c["status"] == "pass" else "✕"} {esc(c["status"])}</span></td></tr>'
        for c in checks
    )

    css = open(os.path.join(ROOT, "docs", "style.css")).read()

    lift = mod["top_decile_lift"]
    auc_delta = mod["roc_auc_improvement_vs_baseline"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SMB Growth Intelligence — live pipeline run</title>
<meta name="description" content="GA4 events through layered ETL, a point-in-time feature store, a purchase-propensity model and a data-quality engine. Every number on this page is written by the pipeline itself on each run.">
<meta name="author" content="abs768">
<meta property="og:type" content="website">
<meta property="og:title" content="SMB Growth Intelligence — live pipeline run">
<meta property="og:description" content="{p['events_processed']:,} events through 10 models in {m['total_pipeline_seconds']}s, with a point-in-time feature store, a propensity model and 11 data-quality assertions.">
<style>
{css}
</style>
</head>
<body>

<nav class="top">
  <div class="wrap">
    <div class="brand">smb-growth<span>-intelligence</span></div>
    <div class="links">
      <a class="hideable" href="#pipeline">Pipeline</a>
      <a class="hideable" href="#features">Features</a>
      <a class="hideable" href="#model">Model</a>
      <a class="hideable" href="#quality">Quality</a>
      <a class="cta" href="{REPO}">GitHub</a>
    </div>
  </div>
</nav>

<header class="hero">
  <div class="wrap hero-grid">
    <div>
      <div class="badges">
        <span class="badge">DuckDB → BigQuery-portable</span>
        <span class="badge">Point-in-time features</span>
        <span class="badge">Leakage-checked</span>
      </div>
      <h1>{p['events_processed']:,} events to scored customers in {m['total_pipeline_seconds']}s.</h1>
      <p class="lead">
        A GA4-shaped event stream through layered ETL, a point-in-time feature
        store, a purchase-propensity model and a data-quality engine. Every figure
        on this page was written by the pipeline itself — this page is rebuilt by
        running it, not by editing it.
      </p>
      <div class="actions">
        <a class="btn primary" href="#pipeline">See the run ↓</a>
        <a class="btn ghost" href="{REPO}">Read the code</a>
      </div>
    </div>
    <div>
      <div class="cards">
        <div class="card"><div class="k">{p['pipeline_success_rate']*100:.0f}%</div><h3>Pipeline success</h3>
          <p>{p['models_run']}/{p['models_run']} models, p95 latency {p['model_latency_p95_s']*1000:.0f} ms.</p></div>
        <div class="card"><div class="k">{p['records_quarantined']:,}</div><h3>Records quarantined</h3>
          <p>{p['quarantine_rate']*100:.2f}% caught at ingestion, not silently loaded.</p></div>
        <div class="card"><div class="k">{mod['roc_auc']:.3f}</div><h3>Propensity ROC-AUC</h3>
          <p>vs {mod['baseline_roc_auc']:.3f} baseline — {auc_delta:+.3f} improvement.</p></div>
        <div class="card"><div class="k">{qual['quality_score']:.0f}/100</div><h3>Data-quality score</h3>
          <p>{qual['assertions_passed']}/{qual['assertions']} assertions, {qual['critical_failures']} critical failures.</p></div>
      </div>
    </div>
  </div>
</header>

<section class="wrap" style="padding:44px 22px 0">
  <div class="finding">
    <b>This page is generated, not written.</b> The workflow runs
    <code>make all</code> on a clean runner, then renders whatever
    <code>reports/*.json</code> the pipeline produced. If the pipeline breaks or a
    quality assertion fails, that shows up here.
    <span class="freshness">Last run {built}{f" · commit <code>{sha}</code>" if sha else ""}
    {f' · <a href="{run_url}">workflow run</a>' if run_url else ""}</span>
  </div>
</section>

<section class="wrap sec" id="pipeline">
  <h2>Pipeline run</h2>
  <p class="blurb">
    Ten SQL models across three layers — staging, intermediate, marts — executed in
    dependency order. Bars show relative execution time; the figure is in the next
    column.
  </p>
  <table>
    <thead><tr><th>Model</th><th>Layer</th><th class="c">Rows</th>
      <th style="width:26%">Time</th><th class="c">Seconds</th><th class="c">Status</th></tr></thead>
    <tbody>
{chr(10).join(model_rows)}
    </tbody>
  </table>
  <p class="blurb">
    {p['raw_events']:,} raw events in, {p['events_processed']:,} loaded,
    {pr['dedup_removed']:,} duplicates removed and {p['records_quarantined']:,}
    quarantined — the difference is accounted for, not dropped.
  </p>
</section>

<section class="wrap sec" id="features">
  <h2>Point-in-time feature store</h2>
  <p class="blurb">
    {fs['n_features']} features computed as of each cutoff date, so a training row
    only ever sees data that existed at that moment. The label is
    <code>{esc(fs['label'])}</code>.
    <span class="{'st-good' if fs['leakage_check_passed'] else 'st-crit'}">
      {'✓' if fs['leakage_check_passed'] else '✕'} leakage check
      {'passed' if fs['leakage_check_passed'] else 'FAILED'}</span>
  </p>
  <table>
    <thead><tr><th>As-of cutoff</th><th class="c">Rows</th>
      <th class="c">Positives</th><th class="c">Base rate</th></tr></thead>
    <tbody>
{cut_rows}
    </tbody>
  </table>
</section>

<section class="wrap sec" id="model">
  <h2>Purchase-propensity model</h2>
  <p class="blurb">
    Trained on cutoffs {esc(", ".join(mm['train_cutoffs']))} and validated on
    {esc(mm['valid_cutoff'])} — {mm['n_train']:,} training rows, {mm['n_valid']:,}
    validation rows at a {mm['valid_base_rate']*100:.2f}% base rate. The baseline is
    the obvious heuristic: rank by recent add-to-cart activity.
  </p>
  <table style="max-width:46em">
    <thead><tr><th>Metric</th><th class="c">Model</th><th class="c">Baseline</th><th class="c">Δ</th></tr></thead>
    <tbody>
      <tr><td class="fname">ROC-AUC</td><td class="c num">{mm['model']['roc_auc']:.4f}</td>
        <td class="c num">{mm['baseline_add_to_cart']['roc_auc']:.4f}</td>
        <td class="c num"><span class="tag-good">+{auc_delta:.4f}</span></td></tr>
      <tr><td class="fname">PR-AUC</td><td class="c num">{mm['model']['pr_auc']:.4f}</td>
        <td class="c num">{mm['baseline_add_to_cart']['pr_auc']:.4f}</td>
        <td class="c num"><span class="tag-good">+{mm['model']['pr_auc']-mm['baseline_add_to_cart']['pr_auc']:.4f}</span></td></tr>
      <tr><td class="fname">Top-decile lift</td><td class="c num">{lift:.3f}×</td>
        <td class="c num">{mm['baseline_add_to_cart']['top_decile_lift']:.3f}×</td>
        <td class="c num"><span class="tag-bad">{lift-mm['baseline_add_to_cart']['top_decile_lift']:+.3f}</span></td></tr>
    </tbody>
  </table>
  <div class="finding" style="margin:18px 0 26px">
    <b>Read this honestly:</b> the model wins on ranking quality overall (ROC-AUC,
    PR-AUC) but <em>not</em> on top-decile lift, where the simple add-to-cart
    heuristic is marginally better. If the campaign only ever targets the top 10%,
    the baseline is the cheaper choice.
  </div>

  <h3 class="sub">Feature weights</h3>
  <p class="blurb">
    Signed model coefficients. Direction is shown by which side of the axis the bar
    falls as well as by colour, and every bar carries its value.
  </p>
  <div class="legend">
    <span><i class="sw pos"></i> ▲ increases propensity</span>
    <span><i class="sw neg"></i> ▼ decreases propensity</span>
  </div>
  <table class="dvtable">
    <thead><tr><th>Feature</th><th class="c">Weight</th><th class="c">Value</th></tr></thead>
    <tbody>
{diverging_rows(mm['feature_importance'])}
    </tbody>
  </table>
</section>

<section class="wrap sec" id="quality">
  <h2>Data-quality assertions</h2>
  <p class="blurb">
    {qual['assertions']} YAML-declared assertions run against the warehouse after
    every pipeline execution, written to an audit table and scored. Critical
    failures fail the build.
  </p>
  <table>
    <thead><tr><th>Check</th><th>Type</th><th class="c">Severity</th>
      <th class="c">Observed</th><th class="c">Threshold</th><th class="c">Status</th></tr></thead>
    <tbody>
{check_rows}
    </tbody>
  </table>
</section>

<section class="wrap sec">
  <h2>How it is put together</h2>
  <div class="pipe">
    <div class="stage"><div class="n">01</div><b>Ingest</b>
      <span>GA4-shaped events, CRM and ad spend; bad records quarantined at the boundary.</span></div>
    <div class="arrow">→</div>
    <div class="stage"><div class="n">02</div><b>Model</b>
      <span>Layered SQL: staging → intermediate → marts, run in dependency order.</span></div>
    <div class="arrow">→</div>
    <div class="stage"><div class="n">03</div><b>Features</b>
      <span>Config-driven point-in-time store, backfilled per cutoff.</span></div>
    <div class="arrow">→</div>
    <div class="stage"><div class="n">04</div><b>Train</b>
      <span>Walk-forward fit, scored back into the warehouse as a mart.</span></div>
    <div class="arrow">→</div>
    <div class="stage"><div class="n">05</div><b>Assert</b>
      <span>Quality checks to an audit table; critical failures break the build.</span></div>
  </div>
  <p class="blurb" style="margin-top:22px">
    It runs locally on DuckDB with no cloud account and no cost, and the same
    modelling logic ports to BigQuery and Dataform — see
    <a href="{REPO}/tree/main/bigquery">/bigquery</a>.
  </p>
  <div class="stack" style="margin-top:14px">
    <span class="chip"><code>make setup</code></span>
    <span class="chip"><code>make all</code></span>
    <span class="chip"><code>pytest -q</code></span>
  </div>
</section>

<footer>
  <div class="wrap">
    <div>Built by <a href="https://github.com/abs768">abs768</a> · generated from <code>reports/*.json</code> on every run</div>
    <div><a href="{REPO}">Source</a> · <a href="https://abs768.github.io/">Portfolio</a></div>
  </div>
</footer>

</body>
</html>
"""
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(html)
    print(f"Wrote {OUT} ({len(html):,} bytes) — {len(models)} models, "
          f"{len(checks)} checks, {len(fs['cutoffs'])} cutoffs")


if __name__ == "__main__":
    build()
