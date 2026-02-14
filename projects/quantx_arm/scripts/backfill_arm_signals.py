#!/usr/bin/env python3
"""
Backfill ARM signals into arm_state_history.csv for historical rows.

Signals added:
  spy_trend_score  0-3: count of (EMA10, EMA20, EMA50) that SPY close exceeds
  vix_risk_flag    0/1: 1 if VIX_close > VIX_MA20 else 0
  rs_iwm_spy       float: IWM_close / SPY_close
  vix_close        float: raw VIX close (needed for vix_change_1d computation)
  vix_change_1d    float: VIX_close - VIX_close.shift(1) (shock signal)
  spy_return_1d    float: (SPY_close / SPY_close.shift(1)) - 1
  spy_gap          float: (SPY_open / SPY_close.shift(1)) - 1 (overnight gap)

Data sources:
  SPY, IWM : yfinance
  VIX       : IBKR (existing ib_insync connection, same as arm_regime_engine)
              Falls back to arm_regime_historical.csv if IBKR unavailable.

After running this script, regenerate rf_features.csv and retrain:
  python3 /root/odte_strategy/data/rf_build_features.py
  python3 /root/odte_strategy/scripts/rf_train_once.py

Usage:
  source /root/odte_strategy/venv/bin/activate
  python3 /root/projects/quantx_arm/scripts/backfill_arm_signals.py
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import yfinance as yf

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ARM_HIST    = "/root/odte_strategy/data/arm_state_history.csv"
BACKTEST_CSV = "/root/odte_strategy/data/backtest_results/arm_regime_historical.csv"
IBKR_VIX_MODULE = "/root/projects/quantx_arm"

# ---------------------------------------------------------------------------
# 1. Load arm_state_history
# ---------------------------------------------------------------------------
print("[1] Loading arm_state_history.csv")
df = pd.read_csv(ARM_HIST)
original_len = len(df)

# Detect date column
date_col = "trade_date" if "trade_date" in df.columns else "date"
df[date_col] = pd.to_datetime(df[date_col]).dt.normalize()
df = df.sort_values(date_col).reset_index(drop=True)

min_date = df[date_col].min()
max_date = df[date_col].max()
print(f"    rows: {len(df)}")
print(f"    date range: {min_date.date()} → {max_date.date()}")
empty_mask = df["spy_trend_score"].isna()
print(f"    rows needing backfill: {empty_mask.sum()}")

# ---------------------------------------------------------------------------
# 2. Download windows
# ---------------------------------------------------------------------------
dl_start = (min_date - timedelta(days=120)).strftime("%Y-%m-%d")
dl_end   = (max_date + timedelta(days=5)).strftime("%Y-%m-%d")
print(f"\n[2] Download window: {dl_start} → {dl_end}")

# ---------------------------------------------------------------------------
# 3. SPY + IWM via yfinance
# ---------------------------------------------------------------------------
print("[3] Downloading SPY and IWM from yfinance...")
raw = yf.download(["SPY", "IWM"], start=dl_start, end=dl_end,
                  auto_adjust=True, progress=False)

if isinstance(raw.columns, pd.MultiIndex):
    spy_close = raw["Close"]["SPY"].dropna()
    spy_open  = raw["Open"]["SPY"].dropna()
    iwm_close = raw["Close"]["IWM"].dropna()
else:
    raise SystemExit("Unexpected yfinance column structure")

spy_close.index = pd.to_datetime(spy_close.index).normalize()
spy_open.index  = pd.to_datetime(spy_open.index).normalize()
iwm_close.index = pd.to_datetime(iwm_close.index).normalize()
print(f"    SPY rows: {len(spy_close)}, IWM rows: {len(iwm_close)}")

# ---------------------------------------------------------------------------
# 4. VIX via IBKR (with fallback to backtest CSV)
# ---------------------------------------------------------------------------
print("[4] Fetching VIX history from IBKR...")
vix_series = None

try:
    sys.path.insert(0, IBKR_VIX_MODULE)
    from ib_insync import IB, Index

    ib = IB()
    ib.connect("127.0.0.1", 4002, clientId=992, timeout=8.0)

    contract = Index("VIX", "CBOE")
    ib.qualifyContracts(contract)

    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="2 Y",
        barSizeSetting="1 day",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    ib.disconnect()

    if bars:
        vix_dates  = pd.to_datetime([str(b.date) for b in bars]).normalize()
        vix_closes = [b.close for b in bars]
        vix_series = pd.Series(vix_closes, index=vix_dates, name="vix_close")
        print(f"    IBKR VIX rows: {len(vix_series)} "
              f"({vix_series.index.min().date()} → {vix_series.index.max().date()})")
    else:
        print("    IBKR returned 0 bars — falling back to backtest CSV")

except Exception as e:
    print(f"    IBKR VIX fetch failed ({e}) — falling back to backtest CSV")

if vix_series is None or len(vix_series) == 0:
    print("    Loading VIX from arm_regime_historical.csv")
    bt = pd.read_csv(BACKTEST_CSV, parse_dates=["date"])
    bt["date"] = bt["date"].dt.normalize()
    vix_series = bt.set_index("date")["vix_close"].dropna()
    print(f"    Backtest VIX rows: {len(vix_series)}")

# ---------------------------------------------------------------------------
# 5. Feature engineering
# ---------------------------------------------------------------------------
print("[5] Computing signals on full download range...")

# --- SPY EMAs + trend score ---
spy_df = spy_close.to_frame("close")
spy_df["ema10"] = spy_df["close"].ewm(span=10, adjust=False).mean()
spy_df["ema20"] = spy_df["close"].ewm(span=20, adjust=False).mean()
spy_df["ema50"] = spy_df["close"].ewm(span=50, adjust=False).mean()
spy_df["spy_trend_score"] = (
    (spy_df["close"] > spy_df["ema10"]).astype(int) +
    (spy_df["close"] > spy_df["ema20"]).astype(int) +
    (spy_df["close"] > spy_df["ema50"]).astype(int)
).astype(float)

# --- VIX MA20 + risk flag + change ---
vix_df = vix_series.to_frame("vix_close")
vix_df["vix_ma20"]      = vix_df["vix_close"].rolling(20, min_periods=1).mean()
vix_df["vix_risk_flag"] = (vix_df["vix_close"] > vix_df["vix_ma20"]).astype(float)
vix_df["vix_change_1d"] = vix_df["vix_close"].diff()

# --- IWM/SPY ratio ---
ratio = (iwm_close / spy_close).rename("rs_iwm_spy")

# --- SPY return + overnight gap ---
spy_return_1d = (spy_close / spy_close.shift(1) - 1).rename("spy_return_1d")
spy_gap       = (spy_open  / spy_close.shift(1) - 1).rename("spy_gap")

# --- Combine into one daily feature table ---
feat = pd.DataFrame(index=spy_df.index)
feat = feat.join(spy_df[["spy_trend_score"]], how="left")
feat = feat.join(vix_df[["vix_close", "vix_risk_flag", "vix_change_1d"]], how="left")
feat = feat.join(ratio,         how="left")
feat = feat.join(spy_return_1d, how="left")
feat = feat.join(spy_gap,       how="left")

# Forward-fill gaps (holidays, non-trading days) within 5-day window
feat = feat.reindex(
    pd.bdate_range(feat.index.min(), feat.index.max())
).ffill(limit=5)

NEW_COLS = ["spy_trend_score", "vix_close", "vix_risk_flag", "vix_change_1d",
            "rs_iwm_spy", "spy_return_1d", "spy_gap"]
print(f"    Feature table: {len(feat)} rows")
for c in NEW_COLS:
    print(f"    {c:20s} null: {feat[c].isna().sum()}")

# ---------------------------------------------------------------------------
# 6. Backup
# ---------------------------------------------------------------------------
ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
backup_path = ARM_HIST + f".bak_{ts}"
import shutil
shutil.copy2(ARM_HIST, backup_path)
print(f"\n[6] Backup → {backup_path}")

# ---------------------------------------------------------------------------
# 7. Merge back into arm_state_history (LEFT JOIN — never drop rows)
# ---------------------------------------------------------------------------
print("[7] Merging signals back into arm_state_history...")

feat_reset = feat.reset_index().rename(columns={"index": date_col})
feat_reset[date_col] = pd.to_datetime(feat_reset[date_col]).dt.normalize()

# Only fill empty cells — preserve already-populated live values
MERGE_COLS = ["spy_trend_score", "vix_close", "vix_risk_flag", "vix_change_1d",
              "rs_iwm_spy", "spy_return_1d", "spy_gap"]

rename_map = {c: f"_{c}_new" for c in MERGE_COLS}
df = df.merge(
    feat_reset[[date_col] + MERGE_COLS].rename(columns=rename_map),
    on=date_col, how="left"
)

for col in MERGE_COLS:
    new_col = f"_{col}_new"
    if col not in df.columns:
        df[col] = df[new_col]
    else:
        df[col] = df[col].combine_first(df[new_col])
    df.drop(columns=[new_col], inplace=True)

assert len(df) == original_len, f"Row count changed! {original_len} → {len(df)}"

# ---------------------------------------------------------------------------
# 8. Save
# ---------------------------------------------------------------------------
df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
df.to_csv(ARM_HIST, index=False)
print(f"[8] Saved → {ARM_HIST}")

# ---------------------------------------------------------------------------
# 9. Validation
# ---------------------------------------------------------------------------
print("\n[9] Validation")
df2 = pd.read_csv(ARM_HIST)
print(f"    Total rows: {len(df2)}")
all_new_cols = ["spy_trend_score", "vix_close", "vix_risk_flag", "vix_change_1d",
                "rs_iwm_spy", "spy_return_1d", "spy_gap"]
for col in all_new_cols:
    if col in df2.columns:
        null_n = df2[col].isna().sum()
        fill_pct = (1 - null_n / len(df2)) * 100
        print(f"    {col:20s}: {null_n:3d} nulls, {fill_pct:.1f}% filled")

show_cols = [date_col] + [c for c in all_new_cols if c in df2.columns]
print("\n    First 3 rows:")
print(df2[show_cols].head(3).to_string(index=False))
print("\n    Last 3 rows:")
print(df2[show_cols].tail(3).to_string(index=False))

print("\n    Sanity sample dates:")
for d in ["2026-02-10", "2026-02-13"]:
    hit = df2[df2[date_col] == d]
    if not hit.empty:
        r = hit.iloc[0]
        print(f"    {d}: vix_close={r.get('vix_close','n/a')} vix_chg={r.get('vix_change_1d','n/a')} "
              f"spy_ret={r.get('spy_return_1d','n/a')} spy_gap={r.get('spy_gap','n/a')}")
    else:
        print(f"    {d}: not in arm_state_history")

print("\nDone. Next steps:")
print("  python3 /root/odte_strategy/data/rf_build_features.py")
print("  python3 /root/odte_strategy/scripts/rf_train_once.py")
