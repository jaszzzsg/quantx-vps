import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import yfinance as yf

ET = ZoneInfo("America/New_York")

REALIZED_DAYS_CSV = Path(r"D:\Trading\03_backtests\SPX_0DTE_ARM\spx0dte_realized_by_day.csv")
OUT_DIR = Path("/root/odte_strategy/data")
out = OUT_DIR / "regime_state.json"
OUT_DIR.mkdir(parents=True, exist_ok=True)

EMA_PERIODS = [10, 20, 50]
VIX_MA_PERIOD = 20

def fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, interval="1d", auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df

def compute_regime_for_date(asof_date: pd.Timestamp, spy, iwm, vix) -> dict:
    # Ensure single scalar values (avoid Series ambiguity)
    spy_close = float(spy.loc[asof_date, "Close"].iloc[0] if isinstance(spy.loc[asof_date, "Close"], pd.Series) else spy.loc[asof_date, "Close"])
    iwm_close = float(iwm.loc[asof_date, "Close"].iloc[0] if isinstance(iwm.loc[asof_date, "Close"], pd.Series) else iwm.loc[asof_date, "Close"])
    vix_close = float(vix.loc[asof_date, "Close"].iloc[0] if isinstance(vix.loc[asof_date, "Close"], pd.Series) else vix.loc[asof_date, "Close"])

    # Trend score
    trend_score = 0
    for p in EMA_PERIODS:
        ema_series = spy["Close"].ewm(span=p, adjust=False).mean()
        ema_val = float(ema_series.loc[asof_date].iloc[0] if isinstance(ema_series.loc[asof_date], pd.Series) else ema_series.loc[asof_date])
        if spy_close > ema_val:
            trend_score += 1

    rs_iwm_spy = float(iwm_close / spy_close)

    vix_ma_series = vix["Close"].rolling(VIX_MA_PERIOD).mean()
    vix_ma_val = vix_ma_series.loc[asof_date]
    vix_ma_val = float(vix_ma_val.iloc[0] if isinstance(vix_ma_val, pd.Series) else vix_ma_val)
    vix_risk_flag = int(vix_close > vix_ma_val) if pd.notna(vix_ma_val) else 0

    # Same mapping as your ARM v1
    if trend_score == 3 and rs_iwm_spy >= 0.95 and vix_risk_flag == 0:
        regime = "R0"
    elif trend_score >= 2 and rs_iwm_spy >= 0.90 and vix_risk_flag == 0:
        regime = "R1"
    elif trend_score >= 1 and vix_risk_flag == 0:
        regime = "R1.5"
    elif trend_score <= 1 and vix_risk_flag == 0:
        regime = "R2"
    elif trend_score <= 1 and vix_risk_flag == 1:
        regime = "R3"
    elif trend_score >= 1 and vix_risk_flag == 1:
        regime = "R4"
    else:
        regime = "R5"

    flags = {
        "risk_off": int(regime in ["R3"]),
        "caution": int(regime in ["R2", "R1.5"]),
        "risk_on": int(regime in ["R0", "R1", "R5"]),
    }

    return {
        "regime": regime,
        "scores": {
            "spy_trend_score": trend_score,
            "iwm_spy_rs": rs_iwm_spy,
            "vix_risk_flag": vix_risk_flag,
        },
        "flags": flags,
    }

def main():
    df = pd.read_csv(REALIZED_DAYS_CSV)
    dates = sorted(df["trade_date"].astype(str).unique().tolist())
    print("Realized trade dates:", len(dates))

    start = (pd.to_datetime(dates[0]) - pd.Timedelta(days=40)).strftime("%Y-%m-%d")
    end   = (pd.to_datetime(dates[-1]) + pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    print("Fetching daily bars:", start, "->", end)

    spy = fetch("SPY", start, end)
    iwm = fetch("IWM", start, end)
    vix = fetch("^VIX", start, end)

    if len(spy)==0 or len(iwm)==0 or len(vix)==0:
        raise RuntimeError("YFinance fetch returned empty DF for SPY/IWM/VIX.")

    wrote = 0
    skipped = 0

    for d in dates:
        asof = pd.to_datetime(d)
        out_path = OUT_DIR / f"regime_state_{d}.json"
        try:
            st = compute_regime_for_date(asof, spy, iwm, vix)
            state = {
                "asof_date": d,
                "regime": st["regime"],
                "scores": st["scores"],
                "flags": st["flags"],
                "notes": "ARM V1 state history (from realized days list)"
            }
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            wrote += 1
        except Exception:
            skipped += 1

    print("OUT_DIR:", OUT_DIR)
    print("Wrote states:", wrote)
    print("Skipped dates:", skipped)
    if wrote:
        print("Example file:", str(OUT_DIR / f"regime_state_{dates[0]}.json"))

if __name__ == "__main__":
    main()
