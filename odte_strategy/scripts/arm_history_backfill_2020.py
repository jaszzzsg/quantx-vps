#!/usr/bin/env python3
"""
ARM History Backfill 2020-2024
==============================
Expands arm_state_history.csv backward to 2020-01-02 using
backtest_results/arm_regime_historical.csv as the data source.

Steps:
  1. Confirm arm_regime_historical.csv has required columns
  2. Filter historical rows to 2020-01-02 -> 2024-09-09 (pre-live range)
  3. Map columns + derive risk_off/caution/risk_on from regime
  4. Fetch SPY OHLC from yfinance for spy_return_1d + spy_gap
  5. Concatenate with existing arm_state_history.csv
  6. Compute vix_change_1d on full sorted series (diff)
  7. Save with backup
  8. Rebuild rf_features.csv (add regime_num, regime_change, days_in_regime)
  9. Run market-risk label backfill (dd_next v4_wq25) + retrain RF

Usage:
    source /root/odte_strategy/venv/bin/activate
    python3 /root/odte_strategy/scripts/arm_history_backfill_2020.py
"""
from __future__ import annotations

import os
import json
import shutil
import joblib
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone, timedelta
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, confusion_matrix, classification_report

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HIST_SRC  = "/root/odte_strategy/data/backtest_results/arm_regime_historical.csv"
ARM_HIST  = "/root/odte_strategy/data/arm_state_history.csv"
FEATURES  = "/root/odte_strategy/data/rf_features.csv"
MODEL_OUT = "/root/odte_strategy/data/rf_model.joblib"
META_OUT  = "/root/odte_strategy/data/rf_model_meta.json"
OUTCOMES  = "/root/odte_strategy/data/bull_put_daily_outcomes.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BACKFILL_END = "2024-09-09"   # last day before live tracking started

REGIME_NUM_MAP = {
    "R0": 0.0, "R1": 1.0, "R1.5": 1.5,
    "R2": 2.0, "R3": 3.0, "R4": 4.0, "R5": 5.0,
}

RF_PARAMS = dict(n_estimators=500, max_depth=6, random_state=42,
                 class_weight="balanced_subsample", n_jobs=-1)
TRAIN_SPLIT = 0.70

PREFERRED_COLS = [
    "regime_num", "risk_off", "caution", "risk_on",
    "regime_change", "days_in_regime",
    "spy_trend_score", "vix_risk_flag", "rs_iwm_spy",
    "vix_change_1d", "spy_return_1d", "spy_gap",
]


def regime_flags(reg: str) -> tuple[int, int, int]:
    risk_off = int(reg in ["R3"])
    caution  = int(reg in ["R2", "R4", "R5"])
    risk_on  = int(reg in ["R0", "R1", "R1.5"])
    return risk_off, caution, risk_on


# ---------------------------------------------------------------------------
# [1] Load + inspect arm_regime_historical.csv
# ---------------------------------------------------------------------------
print("[1] Load arm_regime_historical.csv")
assert os.path.exists(HIST_SRC), f"Missing: {HIST_SRC}"
src = pd.read_csv(HIST_SRC)
src["date"] = pd.to_datetime(src["date"]).dt.normalize()
src = src.sort_values("date").reset_index(drop=True)

print(f"    Rows        : {len(src)}")
print(f"    Date range  : {src['date'].min().date()} -> {src['date'].max().date()}")
print(f"    Columns     : {list(src.columns)}")

assert "regime" in src.columns, "ABORT: 'regime' column missing"
print(f"    regime values: {sorted(src['regime'].unique())}")

# ---------------------------------------------------------------------------
# [2] Filter to pre-live range
# ---------------------------------------------------------------------------
print(f"\n[2] Filter to <= {BACKFILL_END}")
hist = src[src["date"] <= pd.to_datetime(BACKFILL_END)].copy()
print(f"    Rows to backfill: {len(hist)}")
print(f"    Range: {hist['date'].min().date()} -> {hist['date'].max().date()}")

# ---------------------------------------------------------------------------
# [3] Build rows in arm_state_history schema
# ---------------------------------------------------------------------------
print("\n[3] Map columns + derive flags")
hist = hist.rename(columns={"iwm_spy_rs": "rs_iwm_spy"})

flags_rows = [regime_flags(r) for r in hist["regime"]]
hist["risk_off"]   = [f[0] for f in flags_rows]
hist["caution"]    = [f[1] for f in flags_rows]
hist["risk_on"]    = [f[2] for f in flags_rows]
hist["arm_regime"] = hist["regime"]
hist = hist.rename(columns={"date": "trade_date"})

backfill_cols = ["trade_date", "arm_regime", "spy_trend_score", "vix_risk_flag",
                 "rs_iwm_spy", "risk_off", "caution", "risk_on", "vix_close"]
hist_rows = hist[backfill_cols].copy()
hist_rows["vix_change_1d"] = None
hist_rows["spy_return_1d"] = None
hist_rows["spy_gap"]       = None
print(f"    Backfill rows built: {len(hist_rows)}")

# ---------------------------------------------------------------------------
# [4] Fetch SPY OHLC from yfinance
# ---------------------------------------------------------------------------
print("\n[4] Fetch SPY OHLC from yfinance")
dl_start = (hist_rows["trade_date"].min() - timedelta(days=10)).strftime("%Y-%m-%d")
dl_end   = (hist_rows["trade_date"].max() + timedelta(days=5)).strftime("%Y-%m-%d")
print(f"    window: {dl_start} -> {dl_end}")

spy_raw = yf.download("SPY", start=dl_start, end=dl_end,
                      auto_adjust=True, progress=False)
if isinstance(spy_raw.columns, pd.MultiIndex):
    spy_raw.columns = spy_raw.columns.get_level_values(0)
spy_raw.index = pd.to_datetime(spy_raw.index).normalize()
spy_raw = spy_raw.sort_index()[["Open", "Close"]].dropna()
print(f"    SPY rows fetched: {len(spy_raw)}")

spy_dates = list(spy_raw.index)
spy_returns, spy_gaps = [], []

for td in hist_rows["trade_date"]:
    if td not in spy_raw.index:
        spy_returns.append(None); spy_gaps.append(None); continue
    pos = spy_dates.index(td)
    if pos == 0:
        spy_returns.append(None); spy_gaps.append(None); continue
    prev_close  = float(spy_raw.iloc[pos - 1]["Close"])
    today_open  = float(spy_raw.loc[td, "Open"])
    today_close = float(spy_raw.loc[td, "Close"])
    spy_returns.append(today_close / prev_close - 1)
    spy_gaps.append(today_open / prev_close - 1)

hist_rows["spy_return_1d"] = spy_returns
hist_rows["spy_gap"]       = spy_gaps
print(f"    spy_return_1d filled: {sum(1 for x in spy_returns if x is not None)} / {len(hist_rows)}")

# ---------------------------------------------------------------------------
# [5] Load existing arm_state_history.csv + concatenate
# ---------------------------------------------------------------------------
print("\n[5] Load existing arm_state_history.csv + merge")
assert os.path.exists(ARM_HIST), f"Missing: {ARM_HIST}"
existing = pd.read_csv(ARM_HIST)
existing["trade_date"] = pd.to_datetime(existing["trade_date"]).dt.normalize()
print(f"    Existing rows: {len(existing)}  "
      f"({existing['trade_date'].min().date()} -> {existing['trade_date'].max().date()})")

hist_rows["trade_date"] = pd.to_datetime(hist_rows["trade_date"]).dt.normalize()
combined = pd.concat([hist_rows, existing], ignore_index=True)
combined = combined.drop_duplicates(subset=["trade_date"], keep="last")
combined = combined.sort_values("trade_date").reset_index(drop=True)
print(f"    Combined rows: {len(combined)}  "
      f"({combined['trade_date'].min().date()} -> {combined['trade_date'].max().date()})")

# ---------------------------------------------------------------------------
# [6] Compute vix_change_1d on full sorted series
# ---------------------------------------------------------------------------
print("\n[6] Compute vix_change_1d on full sorted series")
combined["vix_change_1d"] = combined["vix_close"].astype(float).diff()
print(f"    vix_change_1d filled: {combined['vix_change_1d'].notna().sum()} / {len(combined)}")

# ---------------------------------------------------------------------------
# [7] Save with backup
# ---------------------------------------------------------------------------
print("\n[7] Save arm_state_history.csv")
backup_path = ARM_HIST.replace(".csv", "_pre_backfill_backup.csv")
shutil.copy2(ARM_HIST, backup_path)
print(f"    Backup -> {backup_path}")

combined["trade_date"] = combined["trade_date"].dt.strftime("%Y-%m-%d")
combined.to_csv(ARM_HIST, index=False)
print(f"    Saved  -> {ARM_HIST}  ({len(combined)} rows)")

# ---------------------------------------------------------------------------
# [8] Rebuild rf_features.csv
# ---------------------------------------------------------------------------
print("\n[8] Rebuild rf_features.csv")
df_feat = combined.copy()
df_feat["date"] = pd.to_datetime(df_feat["trade_date"]).dt.normalize()
df_feat = df_feat.sort_values("date").reset_index(drop=True)

df_feat["regime_num"]   = df_feat["arm_regime"].map(REGIME_NUM_MAP)
df_feat["regime_change"] = (
    (df_feat["arm_regime"] != df_feat["arm_regime"].shift(1)).astype(int)
)
df_feat.iloc[0, df_feat.columns.get_loc("regime_change")] = 0

days_in, count = [], 1
for i in range(len(df_feat)):
    if i == 0:
        days_in.append(1); continue
    if df_feat.iloc[i]["regime_change"] == 1:
        count = 1
    else:
        count += 1
    days_in.append(count)
df_feat["days_in_regime"] = days_in

# Preserve existing labels
feat_old = pd.read_csv(FEATURES)
label_map = {}
if "label" in feat_old.columns:
    feat_old["date_dt"] = pd.to_datetime(feat_old["date"]).dt.normalize()
    for _, r in feat_old.iterrows():
        if pd.notna(r.get("label")):
            label_map[r["date_dt"]] = r["label"]
print(f"    Existing labels preserved: {len(label_map)}")
df_feat["label"] = df_feat["date"].map(label_map)

feat_cols = ["date", "arm_regime", "regime_num", "risk_off", "caution", "risk_on",
             "regime_change", "days_in_regime", "spy_trend_score", "vix_risk_flag",
             "rs_iwm_spy", "vix_change_1d", "spy_return_1d", "spy_gap", "label"]
df_feat["date"] = df_feat["date"].dt.strftime("%Y-%m-%d")
df_feat[feat_cols].to_csv(FEATURES, index=False)
print(f"    rf_features.csv saved: {len(df_feat)} rows  "
      f"({df_feat['date'].min()} -> {df_feat['date'].max()})")

# ---------------------------------------------------------------------------
# [9] Label backfill: dd_next v4_wq25
# ---------------------------------------------------------------------------
print("\n[9] Label backfill: dd_next v4_wq25 (worst-quartile adaptive)")

arm = pd.read_csv(ARM_HIST)
arm["date"] = pd.to_datetime(arm["trade_date"]).dt.normalize()
arm = arm.sort_values("date").reset_index(drop=True)
print(f"    ARM rows: {len(arm)}")

print("    Fetching SPY OHLC (full range)...")
dl2_start = (arm["date"].min() - timedelta(days=10)).strftime("%Y-%m-%d")
dl2_end   = (arm["date"].max() + timedelta(days=5)).strftime("%Y-%m-%d")
spy2 = yf.download("SPY", start=dl2_start, end=dl2_end,
                   auto_adjust=True, progress=False)
if isinstance(spy2.columns, pd.MultiIndex):
    spy2.columns = spy2.columns.get_level_values(0)
spy2.index = pd.to_datetime(spy2.index).normalize()
spy2 = spy2.sort_index()[["Open", "Low"]].dropna()
print(f"    SPY rows: {len(spy2)}")

spy_idx2 = list(spy2.index)
next_date_map = {spy_idx2[i]: spy_idx2[i + 1] for i in range(len(spy_idx2) - 1)}

dd_rows = []
for _, r in arm.iterrows():
    d = r["date"]
    d_next = next_date_map.get(d)
    if d_next is None or d_next not in spy2.index:
        dd_rows.append({"date": d, "dd_next": None}); continue
    open_next = float(spy2.loc[d_next, "Open"])
    low_next  = float(spy2.loc[d_next, "Low"])
    dd_rows.append({"date": d, "dd_next": (low_next / open_next) - 1})

dd_df    = pd.DataFrame(dd_rows)
valid_dd = dd_df.dropna(subset=["dd_next"])
print(f"    Valid dd_next rows: {len(valid_dd)} / {len(dd_df)}")

wq25_thresh = float(np.percentile(valid_dd["dd_next"].values, 25))
print(f"    v4_wq25 threshold (Q25): {wq25_thresh:.4f}")

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

label_final = {}
for _, r in arm.iterrows():
    d = r["date"]
    dd_row = dd_df[dd_df["date"] == d]
    if dd_row.empty or pd.isna(dd_row.iloc[0]["dd_next"]):
        continue
    bad = float(dd_row.iloc[0]["dd_next"]) <= wq25_thresh
    if d in outcomes_map:
        oc = outcomes_map[d]
        if oc["breach"] == 1 or oc["full_loss"] == 1:
            bad = True
    label_final[d] = 0 if bad else 1

total_labeled = len(label_final)
n_bad  = sum(1 for v in label_final.values() if v == 0)
n_good = total_labeled - n_bad
bad_rate = n_bad / total_labeled if total_labeled > 0 else float("nan")
print(f"    Labeled: {total_labeled}  GOOD={n_good}  BAD={n_bad}  bad_rate={bad_rate:.3f}")

feat = pd.read_csv(FEATURES)
feat["date_dt"] = pd.to_datetime(feat["date"]).dt.normalize()
feat["label"]   = feat["date_dt"].map(label_final)
feat = feat.drop(columns=["date_dt"])
feat.to_csv(FEATURES, index=False)
print(f"    rf_features.csv updated: {feat['label'].notna().sum()} labeled rows")

# ---------------------------------------------------------------------------
# [10] Train RF on all labeled rows
# ---------------------------------------------------------------------------
print("\n[10] Train RF on all labeled rows")
df = pd.read_csv(FEATURES)
df = df.dropna(subset=["label"]).copy()
df["label"] = df["label"].astype(int)
df["date"]  = pd.to_datetime(df["date"])
df = df.sort_values("date").reset_index(drop=True)
print(f"    Labeled rows: {len(df)}  ({df.date.min().date()} -> {df.date.max().date()})")

usable = [c for c in PREFERRED_COLS if c in df.columns and df[c].notna().mean() >= 0.5]
print(f"    Features ({len(usable)}): {usable}")

X_all = df[usable].fillna(0).astype(float)
y_all = df["label"].astype(int)

clf_full = RandomForestClassifier(**RF_PARAMS)
clf_full.fit(X_all, y_all)
joblib.dump({"model": clf_full, "features": usable}, MODEL_OUT)
print(f"    Model saved -> {MODEL_OUT}")

meta = {
    "trained_at"  : datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    "rows_total"  : len(df),
    "features"    : usable,
    "n_features"  : len(usable),
    "label_dist"  : df["label"].value_counts().to_dict(),
    "label_source": f"v4_wq25 (dd_next <= Q25={wq25_thresh:.4f})",
}
with open(META_OUT, "w") as f:
    json.dump(meta, f, indent=2)
print(f"    Meta  saved -> {META_OUT}")

# ---------------------------------------------------------------------------
# [11] Time-based 70/30 forward validation
# ---------------------------------------------------------------------------
print("\n[11] Time-based 70/30 forward validation")
split_idx = int(len(df) * TRAIN_SPLIT)
train = df.iloc[:split_idx].copy()
test  = df.iloc[split_idx:].copy()
print(f"    train: {len(train)} rows  ({train.date.min().date()} -> {train.date.max().date()})")
print(f"    test : {len(test)} rows  ({test.date.min().date()} -> {test.date.max().date()})")

u2  = [c for c in PREFERRED_COLS if c in train.columns and train[c].notna().mean() >= 0.5]
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
cm = confusion_matrix(yte, preds)
print("    Confusion matrix (rows=actual, cols=predicted):")
print(f"        Actual BAD  | {cm[0,0]:4d} (correctly skipped)  {cm[0,1]:4d} (missed)")
print(f"        Actual GOOD | {cm[1,0]:4d} (over-filtered)       {cm[1,1]:4d} (correctly traded)")
print()
print(classification_report(yte, preds, digits=3, target_names=["BAD(0)", "GOOD(1)"]))

print("    Threshold analysis on test set:")
print(f"    {'threshold':<12} {'trade_rate':<14} {'bad_if_traded':<18} {'baseline'}")
bl = (yte == 0).mean()
for thr in [0.60, 0.65, 0.70]:
    mask = probs >= thr
    if mask.sum() == 0:
        print(f"    {thr:<12.2f} no rows above threshold"); continue
    tr   = mask.mean()
    bad  = (yte[mask] == 0).mean()
    lift = bl / bad if bad > 0 else float("inf")
    print(f"    {thr:<12.2f} {tr:<14.1%} {bad:<18.3f} ({bl:.3f}) -> {lift:.1f}x lift")

print("\n[12] Feature importances (time-split model)")
fi = sorted(zip(u2, clf_ts.feature_importances_), key=lambda x: -x[1])
for name, imp in fi:
    print(f"    {name:20s} {imp:.4f}  {'#' * int(imp * 50)}")

print(f"""
===========================================================
SUMMARY
  arm_state_history rows : {len(combined)}
  Date range             : {combined['trade_date'].min()} -> {combined['trade_date'].max()}
  Labeled rows (RF)      : {total_labeled}
  GOOD / BAD             : {n_good} / {n_bad}  (bad_rate={bad_rate:.3f})
  wq25 threshold         : {wq25_thresh:.4f}
  Forward AUC (70/30)    : {auc:.3f}
  rf_model.joblib        : saved ({len(df)} rows)
===========================================================
""")
