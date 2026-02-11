import os, json
import pandas as pd

ARM_JSON="/root/projects/quantx_arm/state/regime_state.json"
ARM_HIST="/root/odte_strategy/data/arm_state_history.csv"

def main():
    if not os.path.exists(ARM_JSON):
        raise SystemExit(f"Missing {ARM_JSON}")

    with open(ARM_JSON,"r") as f:
        s=json.load(f)

    asof = s.get("asof_date") or s.get("trade_date") or s.get("date")
    if asof is None:
        raise SystemExit("ARM JSON missing asof_date/trade_date/date")

    trade_date = pd.to_datetime(asof).date().isoformat()

    regime = s.get("regime") or s.get("arm_regime")
    flags = s.get("flags", {})
    scores = s.get("scores", {})

    row = {
        "trade_date": trade_date,
        "arm_regime": regime,
        "spy_trend_score": scores.get("spy_trend_score"),
        "vix_risk_flag": scores.get("vix_risk_flag"),
        "rs_iwm_spy": scores.get("iwm_spy_rs"),  # JSON key is iwm_spy_rs
        "risk_off": int(flags.get("risk_off", 0) or 0),
        "caution": int(flags.get("caution", 0) or 0),
        "risk_on": int(flags.get("risk_on", 0) or 0),
    }

    new = pd.DataFrame([row])

    if os.path.exists(ARM_HIST):
        old = pd.read_csv(ARM_HIST)
        df = pd.concat([old, new], ignore_index=True)
    else:
        df = new

    df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date.astype(str)
    df = df.drop_duplicates(subset=["trade_date"], keep="last").sort_values("trade_date")
    df.to_csv(ARM_HIST, index=False)

    print("UPSERTED trade_date:", trade_date)
    print("MAX trade_date now:", df["trade_date"].max())

if __name__ == "__main__":
    main()
