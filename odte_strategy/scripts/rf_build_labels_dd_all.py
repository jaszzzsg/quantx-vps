#!/usr/bin/env python3
"""
RF Label Backfill — Market-Risk Labels for ALL ARM Dates
=========================================================

Problem: current rf_features.csv only labels rows where took_trade==1
(~85 rows). No trades have fired since Dec 2024, so the dataset is stuck.

Solution: label EVERY ARM history date using next-day SPY intraday drawdown,
regardless of whether a trade was actually placed.

NEW LABEL (market-risk, not trade-PnL):
  For each ARM date D:
    D_next = next trading day in SPY calendar (positional shift — no gaps)
    dd_next = (SPY_low[D_next] / SPY_open[D_next]) - 1
    BAD  = 0   if dd_next <= DD_THRESH
    GOOD = 1   otherwise

Optionally incorporates breach/full_loss from bull_put_daily_outcomes.csv
when the row exists, but does NOT require it.

After labeling:
  - Overwrites label column in rf_features.csv
  - Retrains RF inline
  - Runs time-based 70/30 forward validation inline
  - Reports: labeled count, bad_rate, forward AUC, threshold analysis

Usage:
    source /root/odte_strategy/venv/bin/activate
    python3 /root/odte_strategy/scripts/rf_build_labels_dd_all.py
"""
from __future__ import annotations

import os
import random
import json
import joblib
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import timedelta
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, confusion_matrix, classification_report

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DD_THRESH   = -0.007        # must match rf_build_features.py
TRAIN_SPLIT = 0.70          # chronological 70/30
RF_PARAMS   = dict(n_estimators=500, max_depth=6, random_state=42,
                   class_weight="balanced_subsample", n_jobs=-1)
REPORT_THRESHOLDS = [0.60, 0.65, 0.70]

ARM_HIST    = "/root/odte_strategy/data/arm_state_history.csv"
FEATURES    = "/root/odte_strategy/data/rf_features.csv"
OUTCOMES    = "/root/odte_strategy/data/bull_put_daily_outcomes.csv"
MODEL_OUT   = "/root/odte_strategy/data/rf_model.joblib"
META_OUT    = "/root/odte_strategy/data/rf_model_meta.json"

PREFERRED_COLS = [
    "regime_num", "risk_off", "caution", "risk_on",
    "regime_change", "days_in_regime",
    "spy_trend_score", "vix_risk_flag", "rs_iwm_spy",
    "vix_change_1d", "spy_return_1d", "spy_gap",
]

# ---------------------------------------------------------------------------
# [1] Load ARM dates
# ---------------------------------------------------------------------------
print("[1] Load ARM history dates")
arm = pd.read_csv(ARM_HIST)
date_col = "trade_date" if "trade_date" in arm.columns else "date"
arm[date_col] = pd.to_datetime(arm[date_col]).dt.normalize()
arm = arm.sort_values(date_col).reset_index(drop=True)
print(f"    ARM rows : {len(arm)}")
print(f"    date range: {arm[date_col].min().date()} → {arm[date_col].max().date()}")

# ---------------------------------------------------------------------------
# [2] Fetch SPY OHLC from yfinance
# ---------------------------------------------------------------------------
print("\n[2] Fetch SPY OHLC (yfinance)")
dl_start = (arm[date_col].min() - timedelta(days=10)).strftime("%Y-%m-%d")
dl_end   = (arm[date_col].max() + timedelta(days=5)).strftime("%Y-%m-%d")
print(f"    window: {dl_start} → {dl_end}")

spy_raw = yf.download("SPY", start=dl_start, end=dl_end,
                      auto_adjust=True, progress=False)
if isinstance(spy_raw.columns, pd.MultiIndex):
    spy_raw.columns = spy_raw.columns.get_level_values(0)
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy_raw = spy_raw.sort_index()
spy_raw = spy_raw[["Open", "High", "Low", "Close"]].dropna()
print(f"    SPY rows: {len(spy_raw)} ({spy_raw.index.min().date()} → {spy_raw.index.max().date()})")

# ---------------------------------------------------------------------------
# [3] Build next-trading-day mapping (positional shift on SPY calendar)
# ---------------------------------------------------------------------------
print("\n[3] Build next-trading-day mapping (positional shift)")
spy_dates = spy_raw.index  # only trading days — no gaps
next_date_map: dict[pd.Timestamp, pd.Timestamp] = {}
for i, d in enumerate(spy_dates[:-1]):
    next_date_map[d] = spy_dates[i + 1]
# last date has no next → will be NaN

# ---------------------------------------------------------------------------
# [4] Compute dd_next for each ARM date; print 10 random samples
# ---------------------------------------------------------------------------
print("\n[4] Compute dd_next = (SPY_low[D+1] / SPY_open[D+1]) - 1")

rows_dd = []
for _, r in arm.iterrows():
    d = r[date_col]
    d_next = next_date_map.get(d)
    if d_next is None or d_next not in spy_raw.index:
        rows_dd.append({"date": d, "d_next": None,
                        "open_next": None, "low_next": None, "dd_next": None})
        continue
    open_next = float(spy_raw.loc[d_next, "Open"])
    low_next  = float(spy_raw.loc[d_next, "Low"])
    dd_next   = (low_next / open_next) - 1
    rows_dd.append({"date": d, "d_next": d_next,
                    "open_next": open_next, "low_next": low_next, "dd_next": dd_next})

dd_df = pd.DataFrame(rows_dd)
valid_dd = dd_df.dropna(subset=["dd_next"])
print(f"    Rows with valid dd_next: {len(valid_dd)} / {len(dd_df)}")

print("\n    --- 10 random alignment samples ---")
print(f"    {'D (ARM)':<12} {'D_next':<12} {'open_next':>10} {'low_next':>10} {'dd_next':>9}")
sample_idx = random.sample(list(valid_dd.index), min(10, len(valid_dd)))
for i in sorted(sample_idx):
    row = valid_dd.loc[i]
    print(f"    {str(row['date'].date()):<12} {str(row['d_next'].date()):<12} "
          f"{row['open_next']:>10.2f} {row['low_next']:>10.2f} "
          f"{row['dd_next']:>9.4f}")

# ---------------------------------------------------------------------------
# [5] Load optional breach/full_loss from bull_put_daily_outcomes
# ---------------------------------------------------------------------------
print("\n[5] Load optional breach/full_loss")
outcomes_map: dict[pd.Timestamp, dict] = {}
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
    print("    outcomes CSV not found — skipping breach/full_loss overlay")

# ---------------------------------------------------------------------------
# [6] Assign labels to ALL ARM dates
# ---------------------------------------------------------------------------
print("\n[6] Assign market-risk labels to ALL ARM dates")

labels = []
for i, r in arm.iterrows():
    d     = r[date_col]
    dd_row = dd_df[dd_df["date"] == d]
    if dd_row.empty or pd.isna(dd_row.iloc[0]["dd_next"]):
        labels.append(pd.NA)   # no SPY data for next day (e.g. most recent date)
        continue

    dd_val = float(dd_row.iloc[0]["dd_next"])
    bad = dd_val <= DD_THRESH

    # Optional: override with structural breach/full_loss
    if d in outcomes_map:
        oc = outcomes_map[d]
        if oc["breach"] == 1 or oc["full_loss"] == 1:
            bad = True

    labels.append(0 if bad else 1)

arm_labeled = arm.copy()
arm_labeled["label_dd_all"] = labels
arm_labeled["label_dd_all"] = pd.array(arm_labeled["label_dd_all"], dtype=pd.Int64Dtype())

total_labeled = arm_labeled["label_dd_all"].notna().sum()
n_bad  = (arm_labeled["label_dd_all"] == 0).sum()
n_good = (arm_labeled["label_dd_all"] == 1).sum()
baseline_bad = n_bad / total_labeled if total_labeled > 0 else float("nan")

print(f"    Labeled: {total_labeled} / {len(arm_labeled)}")
print(f"    GOOD(1): {n_good}  BAD(0): {n_bad}  bad_rate: {baseline_bad:.3f}")

# ---------------------------------------------------------------------------
# [7] Merge new labels into rf_features.csv
# ---------------------------------------------------------------------------
print("\n[7] Merge labels into rf_features.csv")
feat = pd.read_csv(FEATURES)
feat["date"] = pd.to_datetime(feat["date"]).dt.normalize()

# Build label lookup from arm_labeled
label_map = {
    row[date_col]: row["label_dd_all"]
    for _, row in arm_labeled.iterrows()
    if pd.notna(row["label_dd_all"])
}

feat["label"] = feat["date"].map(label_map)
feat["date"] = feat["date"].dt.strftime("%Y-%m-%d")
feat.to_csv(FEATURES, index=False)

new_labeled = feat["label"].notna().sum()
print(f"    rf_features.csv saved  ({new_labeled} labeled rows, was 85)")

# ---------------------------------------------------------------------------
# [8] Train RF on all labeled rows
# ---------------------------------------------------------------------------
print("\n[8] Train RF (all labeled rows)")

df = pd.read_csv(FEATURES)
df = df.dropna(subset=["label"]).copy()
df["label"] = df["label"].astype(int)
df["date"]  = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)
print(f"    labeled rows: {len(df)}")
print(f"    date range  : {df.date.min().date()} → {df.date.max().date()}")

usable = [c for c in PREFERRED_COLS if c in df.columns and df[c].notna().mean() >= 0.5]
print(f"    features ({len(usable)}): {usable}")

X_all = df[usable].fillna(0).astype(float)
y_all = df["label"].astype(int)

clf_full = RandomForestClassifier(**RF_PARAMS)
clf_full.fit(X_all, y_all)

joblib.dump({"model": clf_full, "features": usable}, MODEL_OUT)
print(f"    Model saved → {MODEL_OUT}")

from datetime import datetime, timezone
meta = {
    "trained_at"  : datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "rows_total"  : len(df),
    "features"    : usable,
    "n_features"  : len(usable),
    "label_dist"  : df["label"].value_counts().to_dict(),
    "label_source": "market_risk_dd_all (dd_next <= -0.007)",
}
with open(META_OUT, "w") as f:
    json.dump(meta, f, indent=2)
print(f"    Meta  saved → {META_OUT}")

# ---------------------------------------------------------------------------
# [9] Time-based 70/30 forward validation
# ---------------------------------------------------------------------------
print("\n[9] Time-based 70/30 forward validation")

split_idx = int(len(df) * TRAIN_SPLIT)
train = df.iloc[:split_idx].copy()
test  = df.iloc[split_idx:].copy()
print(f"    train: {len(train)} rows  ({train.date.min().date()} → {train.date.max().date()})")
print(f"    test : {len(test)} rows  ({test.date.min().date()} → {test.date.max().date()})")

u2 = [c for c in PREFERRED_COLS if c in train.columns and train[c].notna().mean() >= 0.5]
Xtr = train[u2].fillna(0).astype(float)
ytr = train["label"].astype(int)
Xte = test[u2].fillna(0).astype(float)
yte = test["label"].astype(int)

clf_ts = RandomForestClassifier(**RF_PARAMS)
clf_ts.fit(Xtr, ytr)

probs = clf_ts.predict_proba(Xte)[:, 1]
preds = clf_ts.predict(Xte)

acc = (preds == yte).mean()
try:
    auc = roc_auc_score(yte, probs)
except Exception:
    auc = float("nan")

print(f"\n    Accuracy : {acc:.3f}")
print(f"    AUC      : {auc:.3f}")
print()
cm = confusion_matrix(yte, preds)
print("    Confusion matrix (rows=actual, cols=predicted):")
print(f"        Actual BAD  | {cm[0,0]:4d} (correctly skipped)  {cm[0,1]:4d} (missed — traded when BAD)")
print(f"        Actual GOOD | {cm[1,0]:4d} (over-filtered)       {cm[1,1]:4d} (correctly traded)")
print()
print(classification_report(yte, preds, digits=3, target_names=["BAD(0)", "GOOD(1)"]))

print("    Threshold analysis on test set:")
print(f"    {'threshold':<12} {'trade_rate':<14} {'bad_if_traded':<18} {'baseline'}")
bl = (yte == 0).mean()
for thr in REPORT_THRESHOLDS:
    mask = probs >= thr
    if mask.sum() == 0:
        print(f"    {thr:<12.2f} no rows above threshold")
        continue
    tr   = mask.mean()
    bad  = (yte[mask] == 0).mean()
    lift = bl / bad if bad > 0 else float("inf")
    print(f"    {thr:<12.2f} {tr:<14.1%} {bad:<18.3f} ({bl:.3f}) → {lift:.1f}x lift")

print("\n[10] Feature importances (time-split model)")
fi = sorted(zip(u2, clf_ts.feature_importances_), key=lambda x: -x[1])
for name, imp in fi:
    bar = "#" * int(imp * 50)
    print(f"    {name:20s} {imp:.4f}  {bar}")

print(f"""
===========================================================
SUMMARY
  ARM dates labeled   : {total_labeled}
  GOOD / BAD          : {n_good} / {n_bad}  (bad_rate={baseline_bad:.3f})
  Forward AUC (70/30) : {auc:.3f}
  Label source        : dd_next = (SPY_low[D+1]/SPY_open[D+1])-1 <= {DD_THRESH}
  rf_features.csv     : updated ({new_labeled} labeled rows)
  rf_model.joblib     : saved (trained on all {len(df)} labeled rows)
===========================================================
""")
