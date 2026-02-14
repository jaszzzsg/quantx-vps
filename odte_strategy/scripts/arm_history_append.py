import os, json
from datetime import timedelta
import pandas as pd
import yfinance as yf

ARM_JSON="/root/projects/quantx_arm/state/regime_state.json"
ARM_HIST="/root/odte_strategy/data/arm_state_history.csv"


def fetch_spy_ohlc_today(trade_date_str: str):
    """Fetch SPY OHLC for today and yesterday from yfinance to compute return + gap."""
    try:
        dl_start = (pd.to_datetime(trade_date_str) - timedelta(days=10)).strftime("%Y-%m-%d")
        dl_end   = (pd.to_datetime(trade_date_str) + timedelta(days=2)).strftime("%Y-%m-%d")
        spy = yf.download("SPY", start=dl_start, end=dl_end,
                          auto_adjust=True, progress=False)
        if isinstance(spy.columns, pd.MultiIndex):
            spy.columns = spy.columns.get_level_values(0)
        spy.index = pd.to_datetime(spy.index).normalize()
        spy = spy.sort_index()

        today_rows = spy[spy.index <= pd.to_datetime(trade_date_str)]
        if len(today_rows) < 2:
            return None, None

        today = today_rows.iloc[-1]
        prev  = today_rows.iloc[-2]

        spy_return_1d = float(today["Close"] / prev["Close"] - 1)
        spy_gap       = float(today["Open"]  / prev["Close"] - 1)
        return spy_return_1d, spy_gap
    except Exception as e:
        print(f"[warn] SPY fetch failed: {e}")
        return None, None


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
    flags  = s.get("flags", {})
    scores = s.get("scores", {})
    market = s.get("market", {})

    # VIX close from IBKR (already in regime_state.json)
    vix_close_today = market.get("vix_close")

    # Compute vix_change_1d from previous row in arm_state_history
    vix_change_1d = None
    if os.path.exists(ARM_HIST) and vix_close_today is not None:
        hist = pd.read_csv(ARM_HIST)
        if "vix_close" in hist.columns and len(hist) > 0:
            prev_vix = hist["vix_close"].dropna()
            if len(prev_vix) > 0:
                vix_change_1d = float(vix_close_today) - float(prev_vix.iloc[-1])

    # SPY return + gap from yfinance
    spy_return_1d, spy_gap = fetch_spy_ohlc_today(trade_date)

    row = {
        "trade_date":      trade_date,
        "arm_regime":      regime,
        "spy_trend_score": scores.get("spy_trend_score"),
        "vix_risk_flag":   scores.get("vix_risk_flag"),
        "rs_iwm_spy":      scores.get("iwm_spy_rs"),   # JSON key is iwm_spy_rs
        "risk_off":        int(flags.get("risk_off", 0) or 0),
        "caution":         int(flags.get("caution", 0) or 0),
        "risk_on":         int(flags.get("risk_on",  0) or 0),
        "vix_close":       vix_close_today,
        "vix_change_1d":   vix_change_1d,
        "spy_return_1d":   spy_return_1d,
        "spy_gap":         spy_gap,
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
    print(f"  vix_close={vix_close_today}  vix_change_1d={vix_change_1d}  "
          f"spy_return_1d={spy_return_1d}  spy_gap={spy_gap}")
    print("MAX trade_date now:", df["trade_date"].max())

if __name__ == "__main__":
    main()
