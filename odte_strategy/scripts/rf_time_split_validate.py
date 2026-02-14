#!/usr/bin/env python3
"""
Time-based split validation for RF model.

Verifies that model performance holds out-of-sample on a forward time window
(not a random shuffle), which is the correct test for a trading signal.

Split: Train on earliest 70% of labeled dates, test on latest 30%.
Uses identical RF params as rf_train_once.py.

Usage:
    source /root/odte_strategy/venv/bin/activate
    python3 /root/odte_strategy/scripts/rf_time_split_validate.py
"""
import os
import json
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    classification_report, confusion_matrix, roc_auc_score
)

DATA_DIR  = "/root/odte_strategy/data"
FEATURES  = f"{DATA_DIR}/rf_features.csv"
DD_THRESH = -0.007   # must match rf_build_features.py

PREFERRED_COLS = [
    "regime_num", "risk_off", "caution", "risk_on",
    "regime_change", "days_in_regime",
    "spy_trend_score", "vix_risk_flag", "rs_iwm_spy",
    "vix_change_1d", "spy_return_1d", "spy_gap",
]

REPORT_THRESHOLDS = [0.60, 0.65, 0.70]

# ---------------------------------------------------------------------------
print("[1] Load labeled data")
df = pd.read_csv(FEATURES)
df = df.dropna(subset=["label"]).copy()
df["label"] = df["label"].astype(int)
df["date"] = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)
print(f"    labeled rows : {len(df)}")
print(f"    date range   : {df.date.min().date()} → {df.date.max().date()}")
print(f"    GOOD(1)/BAD(0): {(df.label==1).sum()} / {(df.label==0).sum()}")

# ---------------------------------------------------------------------------
print("\n[2] Time-based split (70% train / 30% test — no shuffle)")
split_idx = int(len(df) * 0.70)
train = df.iloc[:split_idx].copy()
test  = df.iloc[split_idx:].copy()
print(f"    train: {len(train)} rows  ({train.date.min().date()} → {train.date.max().date()})")
print(f"    test : {len(test)} rows  ({test.date.min().date()} → {test.date.max().date()})")
print(f"    train BAD: {(train.label==0).sum()}  test BAD: {(test.label==0).sum()}")

# ---------------------------------------------------------------------------
print("\n[3] Select features (>50% fill on train set)")
usable = []
for c in PREFERRED_COLS:
    if c in train.columns:
        fill = train[c].notna().mean()
        if fill >= 0.5:
            usable.append(c)
        else:
            print(f"    skipping {c}: {fill:.0%} fill in train")
print(f"    features ({len(usable)}): {usable}")

Xtr = train[usable].fillna(0).astype(float)
ytr = train["label"].astype(int)
Xte = test[usable].fillna(0).astype(float)
yte = test["label"].astype(int)

# ---------------------------------------------------------------------------
print("\n[4] Train RF (same params as rf_train_once.py)")
clf = RandomForestClassifier(
    n_estimators=500,
    max_depth=6,
    random_state=42,
    class_weight="balanced_subsample",
    n_jobs=-1,
)
clf.fit(Xtr, ytr)

# ---------------------------------------------------------------------------
print("\n[5] Evaluate on held-out test set (latest 30% of dates)")
probs = clf.predict_proba(Xte)[:, 1]
preds = clf.predict(Xte)

acc = (preds == yte).mean()
try:
    auc = roc_auc_score(yte, probs)
except Exception:
    auc = float("nan")

print(f"\n    Accuracy : {acc:.3f}")
print(f"    AUC      : {auc:.3f}")
print()
print("    Confusion matrix (rows=actual, cols=predicted):")
cm = confusion_matrix(yte, preds)
print(f"        Actual BAD  | {cm[0,0]:4d} (correctly skipped)  {cm[0,1]:4d} (missed — traded when BAD)")
print(f"        Actual GOOD | {cm[1,0]:4d} (over-filtered)       {cm[1,1]:4d} (correctly traded)")
print()
print(classification_report(yte, preds, digits=3, target_names=["BAD(0)", "GOOD(1)"]))

# ---------------------------------------------------------------------------
print("    Threshold analysis on test set:")
print(f"    {'threshold':<12} {'trade_rate':<14} {'bad_if_traded':<18} {'baseline_bad'}")
baseline_bad = (yte == 0).mean()
for thr in REPORT_THRESHOLDS:
    mask = probs >= thr
    if mask.sum() == 0:
        print(f"    {thr:<12.2f} no rows above threshold")
        continue
    trade_rate   = mask.mean()
    bad_in_trade = (yte[mask] == 0).mean()
    lift = baseline_bad / bad_in_trade if bad_in_trade > 0 else float("inf")
    print(f"    {thr:<12.2f} {trade_rate:<14.1%} {bad_in_trade:<18.3f} ({baseline_bad:.3f}) → {lift:.1f}x lift")

# ---------------------------------------------------------------------------
print("\n[6] Feature importances")
fi = sorted(zip(usable, clf.feature_importances_), key=lambda x: -x[1])
for name, imp in fi:
    bar = "#" * int(imp * 50)
    print(f"    {name:20s} {imp:.4f}  {bar}")

# ---------------------------------------------------------------------------
print("\n[7] Score distribution on test set")
for pct in [10, 25, 50, 75, 90]:
    print(f"    p{pct}: {np.percentile(probs, pct):.3f}")

print("\nDone — this is an out-of-sample forward test (no leakage).")
