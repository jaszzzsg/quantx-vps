#!/usr/bin/env python3
"""
RF Train — SPX Bull Put (upgraded)
Uses all available features from rf_features.csv.
Saves model + metadata (trained_at date) for audit trail.
"""
import os
import json
import joblib
import pandas as pd
from datetime import datetime, timezone
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix

DATA_DIR = "/root/odte_strategy/data"
FEATURES = f"{DATA_DIR}/rf_features.csv"
MODEL_OUT = f"{DATA_DIR}/rf_model.joblib"
META_OUT = f"{DATA_DIR}/rf_model_meta.json"

# Prefer richer features if populated, always fall back gracefully
PREFERRED_COLS = [
    "regime_num", "risk_off", "caution", "risk_on",
    "regime_change", "days_in_regime",
    "spy_trend_score", "vix_risk_flag", "rs_iwm_spy",
]
MIN_COLS = ["regime_num", "risk_off", "caution", "risk_on"]

print("[1] load data")
df = pd.read_csv(FEATURES)
df = df.dropna(subset=["label"]).copy()
df["label"] = df["label"].astype(int)
print(f"    labeled rows: {len(df)}")

# Use preferred cols that have enough data (>50% filled)
usable = []
for c in PREFERRED_COLS:
    if c in df.columns:
        fill_rate = df[c].notna().sum() / len(df)
        if fill_rate >= 0.5:
            usable.append(c)
        else:
            print(f"    skipping {c}: only {fill_rate:.0%} filled")

if len(usable) < len(MIN_COLS):
    usable = [c for c in MIN_COLS if c in df.columns]

print(f"    features used ({len(usable)}): {usable}")

X = df[usable].fillna(0).astype(float)
y = df["label"].astype(int)

print("[2] split")
if len(df) >= 20:
    Xtr, Xte, ytr, yte = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )
else:
    # Too few samples for stratified split — train on all
    Xtr, Xte, ytr, yte = X, X, y, y
    print("    WARNING: <20 labeled rows, training on full set")

print("[3] train RF")
clf = RandomForestClassifier(
    n_estimators=500,
    max_depth=6,
    random_state=42,
    class_weight="balanced_subsample",
    n_jobs=-1,
)
clf.fit(Xtr, ytr)

print("[4] eval")
pred = clf.predict(Xte)
print("Confusion matrix:\n", confusion_matrix(yte, pred))
print("\nReport:\n", classification_report(yte, pred, digits=3))

print("[5] save model")
joblib.dump({"model": clf, "features": usable}, MODEL_OUT)
print("WROTE:", MODEL_OUT)

# Save metadata — this is the "last trained date" log
meta = {
    "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "rows_total": len(df),
    "features": usable,
    "n_features": len(usable),
    "label_dist": df["label"].value_counts().to_dict(),
}
with open(META_OUT, "w") as f:
    json.dump(meta, f, indent=2)
print("META:", META_OUT)
print(json.dumps(meta, indent=2))
