"""Generate a GA4-shaped synthetic ecommerce dataset for the local (DuckDB) prototype.

The real GCP build points at Google's public `bigquery-public-data.ga4_obfuscated_sample_ecommerce`
dataset instead (see /bigquery). This generator produces the same *shape* of data so the
transformation, feature and quality logic is identical across both engines.

Design goals that make the downstream analytics tell a coherent SMB-growth story:
  * A view -> add_to_cart -> begin_checkout -> purchase funnel with realistic drop-off.
  * Campaigns with higher ad spend attract more sessions AND convert better (so ROAS varies).
  * "Showcase" products that are viewed a lot but rarely purchased.
  * Signup cohorts with differing retention.
  * A small amount of deliberately dirty data (dupes, nulls, negative revenue) so the
    data-quality layer has something real to quarantine.
"""
from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw")

START_DATE = datetime(2025, 4, 1)
DAYS = 90
N_USERS = 9000
KNOWN_FRACTION = 0.55          # share of users mapped to a CRM customer_id
SEED = 42

DEVICES = (["mobile", "desktop", "tablet"], [0.62, 0.31, 0.07])
COUNTRIES = (
    ["United States", "India", "United Kingdom", "Canada", "Germany", "Australia"],
    [0.45, 0.15, 0.12, 0.10, 0.10, 0.08],
)

# campaign_id, channel, source, medium, daily_spend, quality (conv multiplier)
CAMPAIGNS = [
    ("cmp_brand_search", "paid_search", "google", "cpc", 420.0, 1.35),
    ("cmp_generic_search", "paid_search", "google", "cpc", 300.0, 1.05),
    ("cmp_shopping", "shopping", "google", "cpc", 380.0, 1.20),
    ("cmp_meta_prospecting", "paid_social", "facebook", "cpc", 260.0, 0.80),
    ("cmp_meta_retargeting", "paid_social", "facebook", "cpc", 150.0, 1.45),
    ("cmp_email_newsletter", "email", "newsletter", "email", 20.0, 1.25),
    ("cmp_display", "display", "gdn", "banner", 180.0, 0.60),
    ("cmp_organic", "organic", "google", "organic", 0.0, 1.00),
]

CATEGORIES = ["Apparel", "Drinkware", "Bags", "Electronics", "Office", "Accessories"]


def build_products(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    for i in range(40):
        cat = rng.choice(CATEGORIES)
        price = float(np.round(rng.uniform(9, 180), 2))
        # ~20% of products are "showcase": high view weight, low purchase propensity.
        showcase = rng.random() < 0.20
        view_weight = float(rng.uniform(2.0, 4.0) if showcase else rng.uniform(0.5, 2.0))
        purchase_prop = float(rng.uniform(0.15, 0.45) if showcase else rng.uniform(0.5, 1.3))
        rows.append(
            dict(
                item_id=f"prod_{i:03d}",
                item_name=f"{cat} Item {i:03d}",
                item_category=cat,
                price=price,
                view_weight=view_weight,
                purchase_prop=purchase_prop,
            )
        )
    return pd.DataFrame(rows)


def build_users(rng: np.random.Generator) -> pd.DataFrame:
    n = N_USERS
    known = rng.random(n) < KNOWN_FRACTION
    signup_offset = rng.integers(0, DAYS, n)  # cohort day
    # Bimodal intent: a ~25% high-intent segment vs. a low-intent majority. This creates a
    # learnable signal (as in real ecommerce) that shows up in both history and future purchases.
    high_intent = rng.random(n) < 0.25
    propensity = np.where(high_intent, rng.beta(5.0, 3.0, n), rng.beta(1.5, 10.0, n))
    df = pd.DataFrame(
        dict(
            user_pseudo_id=[f"u{100000 + i}" for i in range(n)],
            customer_id=[f"cust_{i:06d}" if known[i] else None for i in range(n)],
            engagement=rng.lognormal(mean=0.0, sigma=0.5, size=n),   # session frequency driver
            propensity=propensity,                                   # base purchase propensity
            device=rng.choice(DEVICES[0], p=DEVICES[1], size=n),
            country=rng.choice(COUNTRIES[0], p=COUNTRIES[1], size=n),
            acq_campaign=rng.integers(0, len(CAMPAIGNS), n),
            signup_day=signup_offset,
        )
    )
    return df


def generate(seed: int = SEED) -> dict:
    rng = np.random.default_rng(seed)
    products = build_products(rng)
    users = build_users(rng)
    camp_quality = np.array([c[5] for c in CAMPAIGNS])

    prod_idx = np.arange(len(products))
    prod_view_w = products["view_weight"].to_numpy()
    prod_view_p = prod_view_w / prod_view_w.sum()
    prod_price = products["price"].to_numpy()
    prod_pp = products["purchase_prop"].to_numpy()

    events = []
    eid = 0

    # Number of sessions per user driven by engagement and acquisition-campaign quality.
    lam = 1.2 + 2.3 * users["engagement"].to_numpy() * camp_quality[users["acq_campaign"].to_numpy()]
    n_sessions = rng.poisson(lam).clip(1, 25)

    uids = users["user_pseudo_id"].to_numpy()
    cids = users["customer_id"].to_numpy()
    devices = users["device"].to_numpy()
    countries = users["country"].to_numpy()
    acq = users["acq_campaign"].to_numpy()
    prop = users["propensity"].to_numpy()
    eng = users["engagement"].to_numpy()
    eng_mean = float(eng.mean())
    signup_day = users["signup_day"].to_numpy()

    for ui in range(len(users)):
        ns = int(n_sessions[ui])
        # sessions in chronological order so repeat-purchase momentum is well defined
        days_seq = sorted(
            int(min(DAYS - 1, signup_day[ui] + rng.integers(0, max(1, DAYS - signup_day[ui]))))
            for _ in range(ns)
        )
        last_purchase_day = -999
        for day in days_seq:
            # 70% sessions from acquisition campaign, else a re-engagement/organic mix
            if rng.random() < 0.70:
                ci = int(acq[ui])
            else:
                ci = int(rng.choice([4, 5, 7]))  # retargeting / email / organic
            camp = CAMPAIGNS[ci]
            q = camp[5]
            sess_dt = START_DATE + timedelta(
                days=day, hours=int(rng.integers(0, 24)), minutes=int(rng.integers(0, 60))
            )
            session_id = f"{uids[ui]}.{int(sess_dt.timestamp())}"
            t = sess_dt

            def emit(name, item=None, revenue=None, qty=None):
                nonlocal eid, t
                t = t + timedelta(seconds=int(rng.integers(5, 120)))
                events.append(
                    dict(
                        event_id=f"evt_{eid:08d}",
                        event_timestamp=t,
                        event_date=t.date(),
                        event_name=name,
                        user_pseudo_id=uids[ui],
                        customer_id=cids[ui],
                        ga_session_id=session_id,
                        device_category=devices[ui],
                        country=countries[ui],
                        campaign_id=camp[0],
                        traffic_source=camp[1],
                        traffic_medium=camp[3],
                        item_id=item["item_id"] if item is not None else None,
                        item_category=item["item_category"] if item is not None else None,
                        item_name=item["item_name"] if item is not None else None,
                        quantity=qty,
                        purchase_revenue=revenue,
                    )
                )
                eid += 1

            emit("session_start")
            for _ in range(int(rng.integers(1, 5))):
                emit("page_view")

            # view_item stage
            p_view = min(0.95, 0.55 * q + 0.06 * eng[ui])
            if rng.random() < p_view:
                n_items = int(rng.integers(1, 4))
                chosen = rng.choice(prod_idx, size=n_items, replace=False, p=prod_view_p)
                cart = []
                for pi in chosen:
                    emit("view_item", item=products.iloc[pi])
                    # add_to_cart
                    if rng.random() < 0.42 * q * (0.6 + prod_pp[pi] / 2):
                        emit("add_to_cart", item=products.iloc[pi], qty=int(rng.integers(1, 3)))
                        cart.append(pi)
                # begin_checkout + purchase from cart
                if cart and rng.random() < 0.5:
                    emit("begin_checkout")
                    # Future purchase depends on persistent intent, recent engagement momentum,
                    # AND recent-purchase loyalty -- all captured by the behavioral features, which
                    # is exactly why the model can beat a naive baseline.
                    loyalty = 1.7 if (day - last_purchase_day) <= 30 else 1.0
                    p_purchase = min(
                        0.9,
                        0.30 * q * (0.2 + 1.7 * prop[ui]) * (0.7 + 0.5 * eng[ui] / eng_mean)
                        * loyalty * float(np.mean(prod_pp[cart])),
                    )
                    if rng.random() < p_purchase:
                        last_purchase_day = day
                        for pi in cart:
                            qn = int(rng.integers(1, 3))
                            emit("purchase", item=products.iloc[pi], revenue=float(prod_price[pi] * qn), qty=qn)

    df = pd.DataFrame(events)

    # ---- inject deliberate dirty data so the DQ layer has something to catch ----
    n = len(df)
    dupes = df.sample(frac=0.006, random_state=seed)           # ~0.6% exact duplicate event rows
    null_idx = rng.choice(n, size=int(n * 0.003), replace=False)
    df.loc[null_idx, "user_pseudo_id"] = None                  # ~0.3% null user id (should be quarantined)
    neg_idx = df[df.event_name == "purchase"].sample(frac=0.01, random_state=seed).index
    df.loc[neg_idx, "purchase_revenue"] = df.loc[neg_idx, "purchase_revenue"] * -1  # negative revenue
    df = pd.concat([df, dupes], ignore_index=True)
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)  # shuffle

    # ---- ad spend (daily per campaign, correlated with observed sessions) ----
    spend_rows = []
    for d in range(DAYS):
        date = (START_DATE + timedelta(days=d)).date()
        for c in CAMPAIGNS:
            spend = c[4] * float(rng.uniform(0.8, 1.2))
            impressions = int(spend * rng.uniform(30, 60)) if spend > 0 else 0
            clicks = int(impressions * rng.uniform(0.01, 0.04)) if impressions else 0
            spend_rows.append(
                dict(date=date, campaign_id=c[0], channel=c[1], source=c[2],
                     impressions=impressions, clicks=clicks, cost=round(spend, 2))
            )
    ad_spend = pd.DataFrame(spend_rows)

    # ---- CRM customers ----
    crm = users[users["customer_id"].notna()].copy()
    crm["signup_date"] = crm["signup_day"].apply(lambda d: (START_DATE + timedelta(days=int(d))).date())
    crm["plan"] = rng.choice(["free", "starter", "growth", "pro"], size=len(crm), p=[0.4, 0.3, 0.2, 0.1])
    crm["region"] = crm["country"]
    crm = crm[["customer_id", "signup_date", "plan", "region"]].reset_index(drop=True)

    return {"events": df, "ad_spend": ad_spend, "crm_customers": crm}


def write_parquet(tables: dict) -> None:
    con = duckdb.connect()
    for name, df in tables.items():
        out_dir = os.path.join(RAW_DIR, name)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{name}.parquet")
        con.register("df", df)
        con.execute(f"COPY df TO '{path}' (FORMAT PARQUET)")
        con.unregister("df")
        print(f"  wrote {len(df):>8,} rows -> {os.path.relpath(path)}")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=SEED)
    args = ap.parse_args()
    print(f"Generating GA4-shaped synthetic dataset (seed={args.seed}) ...")
    tables = generate(args.seed)
    write_parquet(tables)
    print("Raw layer ready under data/raw/ (represents the GCS raw zone).")


if __name__ == "__main__":
    main()
