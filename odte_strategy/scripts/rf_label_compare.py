#!/usr/bin/env python3
"""
RF Label Variant Comparison
============================

Tests 4 label variants for market-risk labeling, all using the same
SPY next-day intraday drawdown formula:
    dd_next = (SPY_low[D+1] / SPY_open[D+1]) - 1

Variants:
  v1  DD_THRESH = -0.007   (current baseline)
  v2  DD_THRESH = -0.010   (harsher — fewer BADs, more focused)
  v3  DD_THRESH = -0.012   (harshest — only significant down moves)
  v4  Worst-quartile       (adaptive: BAD if dd_next <= Q25 of train set)
                            Q25 computed on training rows only — no lookahead

For each variant:
  - Labels all ARM dates (no took_trade requirement)
  - Runs 70/30 chronological forward validation
  - Reports: labeled count, bad_rate, forward AUC, threshold lift at 0.60/0.65/0.70

Optionally incorporates breach/full_loss overlay from bull_put_daily_outcomes.csv.

After comparison, the best variant is written to:
  data/rf_features.csv  (label column updated)
  rf_model.joblib       (retrained on full labeled set)
  rf_model_meta.json
  rf_label_comparison.json  (full results for audit)

Usage:
    source /root/odte_strategy/venv/bin/activate
    python3 /root/odte_strategy/scripts/rf_label_compare.py
"""
from __future__ import annotations

import json, os, shutil
import random
from datetime import timedelta, datetime, timezone

import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, confusion_matrix, classification_report

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TRAIN_SPLIT  = 0.70
REPORT_THRESHOLDS = [0.60, 0.65, 0.70]
RF_PARAMS    = dict(n_estimators=500, max_depth=6, random_state=42,
                    class_weight="balanced_subsample", n_jobs=-1)

# Minimum trade_rate at thr=0.65 to be considered a viable label
# (if the model blocks too many days it becomes useless for paper data collection)
MIN_TRADE_RATE_65 = 0.15   # must keep ≥15% of days as TRADE at thr=0.65

PREFERRED_COLS = [
    "regime_num", "risk_off", "caution", "risk_on",
    "regime_change", "days_in_regime",
    "spy_trend_score", "vix_risk_flag", "rs_iwm_spy",
    "vix_change_1d", "spy_return_1d", "spy_gap",
]

DATA_DIR   = "/root/odte_strategy/data"
ARM_HIST   = f"{DATA_DIR}/arm_state_history.csv"
FEATURES   = f"{DATA_DIR}/rf_features.csv"
OUTCOMES   = f"{DATA_DIR}/bull_put_daily_outcomes.csv"
MODEL_PATH = f"{DATA_DIR}/rf_model.joblib"
META_PATH  = f"{DATA_DIR}/rf_model_meta.json"
COMPARE_OUT= f"{DATA_DIR}/rf_label_comparison.json"

# ---------------------------------------------------------------------------
# [1] Load ARM dates
# ---------------------------------------------------------------------------
print("[1] Load ARM history dates")
arm = pd.read_csv(ARM_HIST)
dc  = "trade_date" if "trade_date" in arm.columns else "date"
arm[dc] = pd.to_datetime(arm[dc]).dt.normalize()
arm = arm.sort_values(dc).reset_index(drop=True)
print(f"    ARM rows: {len(arm)}  ({arm[dc].min().date()} → {arm[dc].max().date()})")

# ---------------------------------------------------------------------------
# [2] Fetch SPY OHLC once
# ---------------------------------------------------------------------------
print("\n[2] Fetch SPY OHLC (yfinance)")
spy_start = (arm[dc].min() - timedelta(days=10)).strftime("%Y-%m-%d")
spy_end   = (arm[dc].max() + timedelta(days=5)).strftime("%Y-%m-%d")
raw = yf.download("SPY", start=spy_start, end=spy_end,
                  auto_adjust=True, progress=False)
if isinstance(raw.columns, pd.MultiIndex):
    raw.columns = raw.columns.get_level_values(0)
raw.index = pd.to_datetime(raw.index).normalize()
spy = raw[["Open", "High", "Low", "Close"]].dropna().sort_index()
print(f"    SPY rows: {len(spy)} ({spy.index.min().date()} → {spy.index.max().date()})")

spy_dates    = spy.index
next_day_map = {spy_dates[i]: spy_dates[i+1] for i in range(len(spy_dates)-1)}

# ---------------------------------------------------------------------------
# [3] Compute dd_next for all ARM dates
# ---------------------------------------------------------------------------
print("\n[3] Compute dd_next for all ARM dates")
dd_series = {}
for _, r in arm.iterrows():
    d = r[dc]
    d_next = next_day_map.get(d)
    if d_next is None or d_next not in spy.index:
        dd_series[d] = None
        continue
    o = float(spy.loc[d_next, "Open"])
    l = float(spy.loc[d_next, "Low"])
    dd_series[d] = (l / o) - 1 if o > 0 else None

arm["dd_next"] = arm[dc].map(dd_series)
valid = arm["dd_next"].dropna()
print(f"    Valid dd_next: {len(valid)} / {len(arm)}")
print(f"    dd_next stats: mean={valid.mean():.4f}  std={valid.std():.4f}  "
      f"min={valid.min():.4f}  p25={valid.quantile(0.25):.4f}  "
      f"p10={valid.quantile(0.10):.4f}  max={valid.max():.4f}")

# ---------------------------------------------------------------------------
# [4] Load optional breach/full_loss overlay
# ---------------------------------------------------------------------------
print("\n[4] Load optional breach/full_loss overlay")
outcomes_map: dict = {}
if os.path.exists(OUTCOMES):
    out = pd.read_csv(OUTCOMES)
    out["date"] = pd.to_datetime(out["date"]).dt.normalize()
    for _, r in out.iterrows():
        outcomes_map[r["date"]] = {
            "breach":    int(r.get("breach",    0) or 0),
            "full_loss": int(r.get("full_loss", 0) or 0),
        }
    print(f"    Loaded {len(outcomes_map)} outcome rows")
else:
    print("    No outcomes file — breach/full_loss overlay disabled")

# ---------------------------------------------------------------------------
# [5] Load rf_features (base, for feature columns)
# ---------------------------------------------------------------------------
print("\n[5] Load rf_features.csv base")
feat_base = pd.read_csv(FEATURES)
feat_base["date"] = pd.to_datetime(feat_base["date"]).dt.normalize()
print(f"    rf_features rows: {len(feat_base)}")

# ---------------------------------------------------------------------------
# Helper: apply label variant to ARM dates
# ---------------------------------------------------------------------------
def apply_labels(arm_df: pd.DataFrame, thresh: float | None,
                 train_dd: pd.Series | None = None) -> pd.Series:
    """
    thresh=None → use worst-quartile (Q25 of train_dd).
    train_dd is used only when thresh is None (adaptive mode).
    """
    if thresh is None:
        # Adaptive: Q25 of dd_next in the TRAINING portion
        if train_dd is None or len(train_dd.dropna()) < 10:
            print("    WARNING: not enough train dd values for quartile — fallback to -0.010")
            thresh = -0.010
        else:
            thresh = float(train_dd.dropna().quantile(0.25))
            print(f"    [worst-quartile] Q25 of train dd_next = {thresh:.4f}")

    labels = []
    for _, r in arm_df.iterrows():
        d   = r[dc]
        dd  = r["dd_next"]

        if pd.isna(dd):
            labels.append(pd.NA)
            continue

        bad = float(dd) <= thresh

        # Optional breach/full_loss overlay
        if d in outcomes_map:
            oc = outcomes_map[d]
            if oc["breach"] == 1 or oc["full_loss"] == 1:
                bad = True

        labels.append(0 if bad else 1)

    return pd.Series(labels, index=arm_df.index, dtype="Int64")


# ---------------------------------------------------------------------------
# Helper: run one forward-validation trial
# ---------------------------------------------------------------------------
def run_validation(df_labeled: pd.DataFrame, variant_name: str) -> dict:
    """
    df_labeled must have 'date' (datetime), 'label' (int), and PREFERRED_COLS.
    Returns a result dict.
    """
    df = df_labeled.dropna(subset=["label"]).copy()
    df["label"] = df["label"].astype(int)
    df = df.sort_values("date").reset_index(drop=True)

    n_labeled = len(df)
    n_bad  = (df["label"] == 0).sum()
    n_good = (df["label"] == 1).sum()

    usable = [c for c in PREFERRED_COLS
              if c in df.columns and df[c].notna().mean() >= 0.5]

    split_idx = int(len(df) * TRAIN_SPLIT)
    train = df.iloc[:split_idx].copy()
    test  = df.iloc[split_idx:].copy()

    Xtr = train[usable].fillna(0).astype(float)
    ytr = train["label"].astype(int)
    Xte = test[usable].fillna(0).astype(float)
    yte = test["label"].astype(int)

    clf = RandomForestClassifier(**RF_PARAMS)
    clf.fit(Xtr, ytr)

    probs = clf.predict_proba(Xte)[:, 1]
    preds = clf.predict(Xte)

    try:
        auc = round(float(roc_auc_score(yte, probs)), 4)
    except Exception:
        auc = None

    acc   = round(float((preds == yte).mean()), 4)
    bl    = round(float((yte == 0).mean()), 4)

    thr_results = {}
    for thr in REPORT_THRESHOLDS:
        mask = probs >= thr
        if mask.sum() == 0:
            thr_results[str(thr)] = {"trade_rate": 0.0, "bad_rate": None, "lift": None}
            continue
        tr   = round(float(mask.mean()), 4)
        bad  = round(float((yte[mask] == 0).mean()), 4)
        lift = round(bl / bad, 2) if bad > 0 else None
        thr_results[str(thr)] = {"trade_rate": tr, "bad_rate": bad, "lift": lift}

    return {
        "variant":       variant_name,
        "n_labeled":     n_labeled,
        "n_bad":         int(n_bad),
        "n_good":        int(n_good),
        "bad_rate":      round(n_bad / n_labeled, 4),
        "train_rows":    len(train),
        "test_rows":     len(test),
        "train_range":   f"{train.date.min().date()} → {train.date.max().date()}",
        "test_range":    f"{test.date.min().date()} → {test.date.max().date()}",
        "accuracy":      acc,
        "forward_auc":   auc,
        "baseline_bad":  bl,
        "thresholds":    thr_results,
        "clf":           clf,   # kept in-memory for potential save, dropped from JSON
        "usable_feats":  usable,
        "df_labeled":    df,    # kept for potential save
    }


# ---------------------------------------------------------------------------
# [6] Run all variants
# ---------------------------------------------------------------------------
print("\n" + "="*65)
print("[6] Run all label variants")
print("="*65)

variants = [
    ("v1_dd007", "DD_THRESH=-0.007 (current baseline)", -0.007, False),
    ("v2_dd010", "DD_THRESH=-0.010 (harsher)",          -0.010, False),
    ("v3_dd012", "DD_THRESH=-0.012 (harshest)",          -0.012, False),
    ("v4_wq25",  "Worst-quartile Q25 (adaptive)",         None,  True),
]

results = []

for vid, vname, thresh, is_adaptive in variants:
    print(f"\n--- {vid}: {vname} ---")

    if is_adaptive:
        # Compute Q25 on training portion of arm dd_next
        split_n = int(len(arm) * TRAIN_SPLIT)
        train_arm = arm.iloc[:split_n]
        arm["label"] = apply_labels(arm, thresh=None,
                                    train_dd=train_arm["dd_next"])
    else:
        arm["label"] = apply_labels(arm, thresh=thresh)

    # Merge into feat_base for feature columns
    label_map = {
        row[dc]: row["label"]
        for _, row in arm.iterrows()
        if pd.notna(row["label"])
    }
    feat = feat_base.copy()
    feat["label"] = feat["date"].map(label_map)

    r = run_validation(feat, vid)
    r["description"] = vname
    r["thresh_value"] = thresh

    print(f"    labeled={r['n_labeled']}  bad={r['n_bad']}  good={r['n_good']}  bad_rate={r['bad_rate']:.3f}")
    print(f"    forward AUC={r['forward_auc']}  accuracy={r['accuracy']:.3f}")
    print(f"    Threshold lift:")
    for thr_k, tv in r["thresholds"].items():
        lift_str = f"{tv['lift']}x" if tv['lift'] is not None else "inf"
        bad_str  = f"{tv['bad_rate']:.3f}" if tv['bad_rate'] is not None else " n/a"
        print(f"      thr={thr_k}  trade_rate={tv['trade_rate']:.1%}  bad_rate={bad_str}  ({r['baseline_bad']:.3f}) → {lift_str}")

    results.append(r)

# ---------------------------------------------------------------------------
# [7] Comparison table
# ---------------------------------------------------------------------------
print("\n" + "="*65)
print("[7] COMPARISON TABLE")
print("="*65)
print(f"\n{'Variant':<14} {'N_bad/N_good':<14} {'bad_rate':<10} {'fwd_AUC':<10} "
      f"{'lift@0.65':<12} {'trade%@0.65':<13} {'lift@0.70':<12} {'trade%@0.70'}")
print("-"*100)
for r in results:
    t65 = r["thresholds"].get("0.65", {})
    t70 = r["thresholds"].get("0.7",  {})
    lift65  = f"{t65.get('lift','?')}x" if t65.get("lift") is not None else "inf"
    trade65 = f"{t65.get('trade_rate',0):.1%}" if t65.get("trade_rate") is not None else "0%"
    lift70  = f"{t70.get('lift','?')}x" if t70.get("lift") is not None else "inf"
    trade70 = f"{t70.get('trade_rate',0):.1%}" if t70.get("trade_rate") is not None else "0%"
    print(f"{r['variant']:<14} {r['n_bad']}/{r['n_good']:<12} {r['bad_rate']:<10.3f} "
          f"{str(r['forward_auc']):<10} {lift65:<12} {trade65:<13} {lift70:<12} {trade70}")

# ---------------------------------------------------------------------------
# [8] Pick best variant
# ---------------------------------------------------------------------------
print("\n" + "="*65)
print("[8] PICK BEST VARIANT")
print("="*65)

# Score each variant:
#   primary  = lift@0.65 (higher is better)
#   secondary = forward_auc
#   constraint = trade_rate@0.65 >= MIN_TRADE_RATE_65
scored = []
for r in results:
    t65 = r["thresholds"].get("0.65", {})
    lift65  = t65.get("lift") or 0.0
    trade65 = t65.get("trade_rate") or 0.0
    auc     = r["forward_auc"] or 0.0
    viable  = trade65 >= MIN_TRADE_RATE_65
    score   = (lift65 * 10 + auc) if viable else -999
    scored.append((score, lift65, trade65, auc, r))

scored.sort(key=lambda x: -x[0])
best_score, best_lift65, best_trade65, best_auc, best = scored[0]

print(f"\n  Best variant: {best['variant']}  ({best['description']})")
print(f"  lift@0.65={best_lift65}x  trade_rate@0.65={best_trade65:.1%}  "
      f"fwd_AUC={best_auc}  bad_rate={best['bad_rate']:.3f}")

if best_score <= 0:
    print("  WARNING: all variants failed MIN_TRADE_RATE_65 constraint — selecting by AUC only")
    best = max(results, key=lambda r: r["forward_auc"] or 0)

# ---------------------------------------------------------------------------
# [9] Write best variant to production
# ---------------------------------------------------------------------------
print(f"\n[9] Writing best variant ({best['variant']}) to production files")

# Update rf_features.csv label column
feat_out = best["df_labeled"].copy()
feat_out["date_str"] = pd.to_datetime(feat_out["date"]).dt.strftime("%Y-%m-%d")
# Preserve original row count — fill unlabeled rows with NaN
feat_all = feat_base.copy()
feat_all["date_str"] = pd.to_datetime(feat_all["date"]).dt.strftime("%Y-%m-%d")
label_final = {
    row["date_str"]: row["label"]
    for _, row in feat_out.iterrows()
}
feat_all["label"] = feat_all["date_str"].map(label_final)
feat_all = feat_all.drop(columns=["date_str"])
feat_all["date"] = pd.to_datetime(feat_all["date"]).dt.strftime("%Y-%m-%d")
feat_all.to_csv(FEATURES, index=False)
print(f"    rf_features.csv saved — {feat_all['label'].notna().sum()} labeled rows")

# Retrain RF on full labeled set
print("    Retraining rf_model.joblib on full labeled set...")
df_full = best["df_labeled"].copy()
X_full  = df_full[best["usable_feats"]].fillna(0).astype(float)
y_full  = df_full["label"].astype(int)
clf_final = RandomForestClassifier(**RF_PARAMS)
clf_final.fit(X_full, y_full)

ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
ts_path = f"{DATA_DIR}/rf_model_{ts}.joblib"
joblib.dump({"model": clf_final, "features": best["usable_feats"]}, ts_path)
joblib.dump({"model": clf_final, "features": best["usable_feats"]}, MODEL_PATH)
print(f"    rf_model.joblib updated  (timestamped: {ts_path})")

meta = {
    "trained_at":    datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "rows_total":    len(df_full),
    "features":      best["usable_feats"],
    "n_features":    len(best["usable_feats"]),
    "label_dist":    df_full["label"].value_counts().to_dict(),
    "label_variant": best["variant"],
    "label_desc":    best["description"],
    "forward_auc":   best["forward_auc"],
}
with open(META_PATH, "w") as f:
    json.dump(meta, f, indent=2)

# ---------------------------------------------------------------------------
# [10] Save comparison results to JSON (strip non-serializable keys)
# ---------------------------------------------------------------------------
save_results = []
for r in results:
    sr = {k: v for k, v in r.items() if k not in ("clf", "df_labeled")}
    sr["selected"] = (r["variant"] == best["variant"])
    save_results.append(sr)

with open(COMPARE_OUT, "w") as f:
    json.dump({
        "run_at":       datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "best_variant": best["variant"],
        "best_desc":    best["description"],
        "results":      save_results,
    }, f, indent=2)
print(f"    Comparison saved → {COMPARE_OUT}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print(f"""
===========================================================
FINAL SUMMARY
  Best variant  : {best['variant']}  ({best['description']})
  Labeled rows  : {best['n_labeled']}  (bad={best['n_bad']}, good={best['n_good']}, rate={best['bad_rate']:.3f})
  Forward AUC   : {best['forward_auc']}
  lift @ 0.65   : {best['thresholds'].get('0.65', {}).get('lift','?')}x  trade_rate={best['thresholds'].get('0.65', {}).get('trade_rate',0):.1%}
  lift @ 0.70   : {best['thresholds'].get('0.7',  {}).get('lift','?')}x  trade_rate={best['thresholds'].get('0.7',  {}).get('trade_rate',0):.1%}
  rf_model.joblib: updated ({best['n_labeled']} rows, {best['forward_auc']} fwd AUC)
  rf_features.csv: updated (label_variant={best['variant']})
  Comparison log: {COMPARE_OUT}
===========================================================
""")
