#!/usr/bin/env python3
"""
Build rf_features.csv from arm_state_history.csv + bull_put_daily_outcomes.csv.

Label logic (BAD=0, GOOD=1):
  BAD when took_trade==1 AND:
    A) breach==1 OR full_loss==1
    OR
    B) next-trading-day SPY intraday drawdown exceeds DD_THRESH
       dd = (next_day_low / next_day_open) - 1
       BAD if dd <= DD_THRESH

  d_close < entry_px intentionally excluded — too noisy.
"""
import os
import re
from datetime import timedelta

import pandas as pd
import yfinance as yf

DATA_DIR = "/root/odte_strategy/data"
ARM_HIST = os.path.join(DATA_DIR, "arm_state_history.csv")
OUTCOMES = os.path.join(DATA_DIR, "bull_put_daily_outcomes.csv")
OUT      = os.path.join(DATA_DIR, "rf_features.csv")

# Tune here: next-day SPY intraday drawdown threshold for BAD label
DD_THRESH = -0.007   # -0.7% drop from open to intraday low


def fetch_spy_next_day_dd(min_date: pd.Timestamp, max_date: pd.Timestamp) -> pd.Series:
    """
    Returns a Series indexed by TRADE date D containing the next-trading-day
    intraday drawdown:  dd = (low_D+1 / open_D+1) - 1
    """
    dl_start = (min_date - timedelta(days=10)).strftime("%Y-%m-%d")
    dl_end   = (max_date + timedelta(days=10)).strftime("%Y-%m-%d")
    spy = yf.download("SPY", start=dl_start, end=dl_end,
                      auto_adjust=True, progress=False)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    spy.index = pd.to_datetime(spy.index).normalize()
    spy = spy.sort_index()
    dd_next = (spy["Low"].shift(-1) / spy["Open"].shift(-1)) - 1
    dd_next.name = "spy_dd_next"
    return dd_next   # index = trade date D, value = D+1 dd

def regime_to_num(reg: str):
    if reg is None:
        return None
    m = re.match(r"^\s*R\s*([0-9]+(?:\.[0-9]+)?)\s*$", str(reg))
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def main():
    if not os.path.exists(ARM_HIST):
        raise SystemExit(f"Missing: {ARM_HIST}")

    arm = pd.read_csv(ARM_HIST)

    if "date" in arm.columns:
        dcol = "date"
    elif "trade_date" in arm.columns:
        dcol = "trade_date"
    else:
        raise SystemExit(f"arm_state_history.csv missing date column. found={list(arm.columns)}")

    if "arm_regime" not in arm.columns:
        raise SystemExit(f"arm_state_history.csv missing arm_regime. found={list(arm.columns)}")

    arm[dcol] = pd.to_datetime(arm[dcol])
    arm = arm.sort_values(dcol).reset_index(drop=True)

    if "regime_num" not in arm.columns:
        arm["regime_num"] = arm["arm_regime"].apply(regime_to_num)

    arm["regime_change"] = (arm["arm_regime"] != arm["arm_regime"].shift(1)).astype(int)
    arm.loc[0, "regime_change"] = 0

    streak = []
    cur = None
    cnt = 0
    for r in arm["arm_regime"].tolist():
        if r == cur:
            cnt += 1
        else:
            cur = r
            cnt = 1
        streak.append(cnt)
    arm["days_in_regime"] = streak

    missing_req = [c for c in ["risk_off", "caution", "risk_on"] if c not in arm.columns]
    if missing_req:
        raise SystemExit(f"arm_state_history.csv missing required cols: {missing_req}. found={list(arm.columns)}")

    optional = [c for c in ["spy_trend_score", "vix_risk_flag", "rs_iwm_spy"] if c in arm.columns]

    cols = [dcol, "arm_regime", "regime_num", "risk_off", "caution", "risk_on", "regime_change", "days_in_regime"] + optional
    feats = arm[cols].copy()
    feats.rename(columns={dcol: "date"}, inplace=True)
    feats["date"] = pd.to_datetime(feats["date"]).dt.strftime("%Y-%m-%d")

    # --- LABEL BUILD ---
    feats["label"] = pd.NA
    if os.path.exists(OUTCOMES):
        out = pd.read_csv(OUTCOMES)
        if "date" not in out.columns:
            raise SystemExit(f"Outcomes missing 'date': {OUTCOMES} cols={list(out.columns)}")

        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")

        required = ["took_trade", "breach", "full_loss"]
        miss = [c for c in required if c not in out.columns]
        if miss:
            raise SystemExit(f"Outcomes missing cols {miss}: {OUTCOMES} cols={list(out.columns)}")

        o = out[["date", "took_trade", "breach", "full_loss"]].copy()
        o["took_trade"] = o["took_trade"].astype(int)
        o["breach"]     = o["breach"].astype(int)
        o["full_loss"]  = o["full_loss"].astype(int)

        # Fetch SPY next-day intraday drawdown
        o_dates = pd.to_datetime(o["date"])
        spy_dd = fetch_spy_next_day_dd(o_dates.min(), o_dates.max())
        spy_dd_df = (spy_dd.reset_index()
                     .rename(columns={"index": "date_dt", "Date": "date_dt"}))
        spy_dd_df.columns = ["date_dt", "spy_dd_next"]
        spy_dd_df["date"] = pd.to_datetime(spy_dd_df["date_dt"]).dt.strftime("%Y-%m-%d")
        o = o.merge(spy_dd_df[["date", "spy_dd_next"]], on="date", how="left")

        traded = o[o.took_trade == 1]
        print(f"[label] DD_THRESH={DD_THRESH}")
        print(f"[label] traded rows    : {len(traded)}")
        print(f"[label] breach==1      : {(traded.breach==1).sum()}")
        print(f"[label] full_loss==1   : {(traded.full_loss==1).sum()}")
        print(f"[label] dd<={DD_THRESH} : {(traded.spy_dd_next <= DD_THRESH).sum()}")
        print(f"[label] combined BAD   : "
              f"{((traded.breach==1)|(traded.full_loss==1)|(traded.spy_dd_next<=DD_THRESH)).sum()}")

        def mk_label(r):
            if r["took_trade"] != 1:
                return pd.NA
            bad = (r["breach"] == 1) or (r["full_loss"] == 1)
            if pd.notna(r["spy_dd_next"]) and r["spy_dd_next"] <= DD_THRESH:
                bad = True
            return 0 if bad else 1

        o["label"] = o.apply(mk_label, axis=1)

        feats = feats.merge(o[["date", "label"]], on="date", how="left", suffixes=("", "_y"))
        feats["label"] = feats["label_y"]
        feats.drop(columns=["label_y"], inplace=True)

    feats.to_csv(OUT, index=False)
    print(f"\nWROTE: {OUT}  rows={len(feats)}  cols={len(feats.columns)}")
    nn = int(feats["label"].notna().sum())
    print(f"LABEL non-null: {nn}")
    if nn:
        vc = feats["label"].dropna().value_counts().to_dict()
        bad_rate = float((feats["label"].dropna() == 0).mean())
        print(f"LABEL counts: {vc}   bad_rate: {bad_rate:.3f}")

if __name__ == "__main__":
    main()
