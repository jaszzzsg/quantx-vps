#!/usr/bin/env python3
import os
import re
import pandas as pd

DATA_DIR = "/root/odte_strategy/data"
ARM_HIST = os.path.join(DATA_DIR, "arm_state_history.csv")
OUTCOMES = os.path.join(DATA_DIR, "bull_put_daily_outcomes.csv")
OUT = os.path.join(DATA_DIR, "rf_features.csv")

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

    # --- LABEL BUILD (stricter) ---
    feats["label"] = pd.NA
    if os.path.exists(OUTCOMES):
        out = pd.read_csv(OUTCOMES)
        if "date" not in out.columns:
            raise SystemExit(f"Outcomes missing 'date': {OUTCOMES} cols={list(out.columns)}")

        out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")

        required = ["took_trade", "breach", "full_loss", "entry_px", "d_close"]
        miss = [c for c in required if c not in out.columns]
        if miss:
            raise SystemExit(f"Outcomes missing cols {miss}: {OUTCOMES} cols={list(out.columns)}")

        o = out[["date", "took_trade", "breach", "full_loss", "entry_px", "d_close"]].copy()
        o["took_trade"] = o["took_trade"].astype(int)
        o["breach"] = o["breach"].astype(int)
        o["full_loss"] = o["full_loss"].astype(int)
        o["entry_px"] = pd.to_numeric(o["entry_px"], errors="coerce")
        o["d_close"] = pd.to_numeric(o["d_close"], errors="coerce")

        def mk_label(r):
            if r["took_trade"] != 1:
                return pd.NA
            # BAD if breached/full loss OR closed below entry_px
            bad = (r["breach"] == 1) or (r["full_loss"] == 1)
            if pd.notna(r["entry_px"]) and pd.notna(r["d_close"]):
                if r["d_close"] < r["entry_px"]:
                    bad = True
            return 0 if bad else 1

        o["label"] = o.apply(mk_label, axis=1)

        feats = feats.merge(o[["date", "label"]], on="date", how="left", suffixes=("", "_y"))
        feats["label"] = feats["label_y"]
        feats.drop(columns=["label_y"], inplace=True)

    feats.to_csv(OUT, index=False)
    print(f"WROTE: {OUT} rows={len(feats)} cols={len(feats.columns)}")
    nn = int(feats["label"].notna().sum())
    print("LABEL non-null:", nn)
    if nn:
        vc = feats["label"].dropna().value_counts().to_dict()
        bad_rate = float((feats["label"].dropna() == 0).mean())
        print("LABEL counts:", vc, "bad_rate:", bad_rate)

if __name__ == "__main__":
    main()
