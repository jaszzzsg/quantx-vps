"""
ARM Regime Backtest
===================
Fetches 6 years of SPY, IWM, VIX data and applies the exact ARM v1 logic
to every trading day. Then measures what the market actually did AFTER each
regime label. Outputs a CSV and a plain-English report.

Think of it like this: for every day the ARM system said "R3 (scary market)",
we look at what happened the next 1, 5, and 21 days. If ARM is right, R3 days
should show bad or flat returns. If R1.5 is actually good, it should show
positive returns. This is how we PROVE each regime label works.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from pathlib import Path
from datetime import datetime

# ========================
# CONFIG
# ========================
START_DATE = "2019-01-01"   # extra buffer for EMA warmup
END_DATE   = datetime.today().strftime("%Y-%m-%d")
EMA_PERIODS = [10, 20, 50]
VIX_MA_PERIOD = 20
OUT_DIR = Path(__file__).resolve().parent
CSV_OUT = OUT_DIR / "arm_regime_historical.csv"
REPORT_OUT = OUT_DIR / "arm_regime_stats_report.txt"

# ========================
# FETCH DATA
# ========================
def fetch(symbol: str, start: str, end: str) -> pd.DataFrame:
    df = yf.download(symbol, start=start, end=end, interval="1d",
                     auto_adjust=True, progress=False)
    if df is None or len(df) == 0:
        raise RuntimeError(f"Empty data for {symbol}")
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df

# ========================
# ARM REGIME LOGIC (V2 — fixed thresholds + R5 early recovery)
# ========================
def classify_regime(trend_score, rs_iwm_spy, vix_risk_flag):
    if trend_score == 3 and rs_iwm_spy >= 0.45 and vix_risk_flag == 0:
        return "R0"    # Perfect bull
    elif trend_score >= 2 and rs_iwm_spy >= 0.40 and vix_risk_flag == 0:
        return "R1"    # Strong bull
    elif trend_score >= 2 and vix_risk_flag == 0:
        return "R1.5"  # Moderate bull
    elif trend_score == 1 and vix_risk_flag == 0:
        return "R5"    # Early recovery
    elif trend_score == 0 and vix_risk_flag == 0:
        return "R2"    # Oversold bounce
    elif trend_score == 0 and vix_risk_flag == 1:
        return "R3"    # Risk-off
    elif trend_score >= 1 and vix_risk_flag == 1:
        return "R4"    # Volatile trend
    else:
        return "R5"    # fallback

# ========================
# BUILD HISTORICAL REGIME SERIES
# ========================
def build_regime_series(spy, iwm, vix):
    records = []

    # Precompute EMAs and VIX MA across full series
    ema_cols = {}
    for p in EMA_PERIODS:
        ema_cols[p] = spy["Close"].ewm(span=p, adjust=False).mean()

    vix_ma = vix["Close"].rolling(VIX_MA_PERIOD).mean()

    # Align on common dates (trading days where all 3 have data)
    common_idx = spy.index.intersection(iwm.index).intersection(vix.index)
    # Drop early warmup period (need at least 50 days for EMA50 + 20 for VIX MA)
    common_idx = common_idx[common_idx >= pd.Timestamp("2020-01-01")]

    def to_scalar(val):
        """Safely convert pandas scalar / Series to float."""
        if hasattr(val, "iloc"):
            return float(val.iloc[0])
        return float(val)

    for date in common_idx:
        try:
            spy_close = to_scalar(spy.loc[date, "Close"])
            iwm_close = to_scalar(iwm.loc[date, "Close"])
            vix_close = to_scalar(vix.loc[date, "Close"])

            # Trend score
            trend_score = sum(
                1 for p in EMA_PERIODS
                if spy_close > to_scalar(ema_cols[p].loc[date])
            )

            # IWM/SPY ratio
            rs = iwm_close / spy_close

            # VIX risk flag (using proper rolling MA — fixes the live engine bug)
            vix_ma_val = to_scalar(vix_ma.loc[date])
            if pd.isna(vix_ma_val):
                vix_risk = 0
            else:
                vix_risk = int(vix_close > float(vix_ma_val))

            regime = classify_regime(trend_score, rs, vix_risk)

            records.append({
                "date": date,
                "spy_close": round(spy_close, 2),
                "iwm_close": round(iwm_close, 2),
                "vix_close": round(vix_close, 2),
                "vix_ma": round(float(vix_ma_val), 2) if not pd.isna(vix_ma_val) else None,
                "spy_trend_score": trend_score,
                "iwm_spy_rs": round(rs, 4),
                "vix_risk_flag": vix_risk,
                "regime": regime,
            })
        except Exception as e:
            continue

    if not records:
        raise RuntimeError("No records built — check data alignment")
    df = pd.DataFrame(records).set_index("date")
    return df

# ========================
# ADD FORWARD RETURNS
# ========================
def add_forward_returns(df, spy):
    spy_close = spy["Close"].reindex(df.index)

    # Next-day return
    spy_next = spy["Close"].shift(-1).reindex(df.index)
    df["ret_1d"] = ((spy_next - spy_close) / spy_close * 100).round(3)

    # Next 5-day return
    spy_5d = spy["Close"].shift(-5).reindex(df.index)
    df["ret_5d"] = ((spy_5d - spy_close) / spy_close * 100).round(3)

    # Next 21-day return
    spy_21d = spy["Close"].shift(-21).reindex(df.index)
    df["ret_21d"] = ((spy_21d - spy_close) / spy_close * 100).round(3)

    # Up or down next day
    df["up_1d"] = (df["ret_1d"] > 0).astype(int)

    return df

# ========================
# GENERATE STATS PER REGIME
# ========================
def regime_stats(df):
    order = ["R0", "R1", "R1.5", "R5", "R2", "R3", "R4"]
    total = len(df)
    rows = []
    for r in order:
        sub = df[df["regime"] == r]
        n = len(sub)
        if n == 0:
            rows.append({"regime": r, "count": 0, "pct": 0})
            continue
        rows.append({
            "regime": r,
            "count": n,
            "pct": round(n / total * 100, 1),
            "avg_ret_1d": round(sub["ret_1d"].mean(), 3),
            "avg_ret_5d": round(sub["ret_5d"].mean(), 3),
            "avg_ret_21d": round(sub["ret_21d"].mean(), 3),
            "win_rate_1d": round(sub["up_1d"].mean() * 100, 1),
            "avg_vix": round(sub["vix_close"].mean(), 1),
            "avg_trend": round(sub["spy_trend_score"].mean(), 2),
            "avg_iwm_rs": round(sub["iwm_spy_rs"].mean(), 4),
        })
    return pd.DataFrame(rows)

# ========================
# WRITE PLAIN-ENGLISH REPORT
# ========================
REGIME_NAMES = {
    "R0": "Perfect Bull",
    "R1": "Strong Bull",
    "R1.5": "Moderate Bull (Large Cap Lead)",
    "R5": "Early Recovery (Green Shoot)",
    "R2": "Oversold Bounce",
    "R3": "Risk-Off (Market Breakdown)",
    "R4": "Volatile Trend (Choppy)",
}

FLAG_NAMES = {
    "R0": "risk_on",
    "R1": "risk_on",
    "R1.5": "risk_on",
    "R5": "caution",
    "R2": "caution",
    "R3": "risk_off",
    "R4": "caution",
}

def write_report(stats_df, df, out_path):
    lines = []
    lines.append("=" * 70)
    lines.append("ARM REGIME BACKTEST REPORT")
    lines.append(f"Period: 2020-01-01 to {END_DATE}  |  Total trading days: {len(df)}")
    lines.append("=" * 70)
    lines.append("")
    lines.append("HOW TO READ THIS REPORT (Explained Simply)")
    lines.append("-" * 40)
    lines.append("Think of each regime like a weather forecast for the stock market:")
    lines.append("  - 'Next 1-day return' = on average, did SPY go UP or DOWN the")
    lines.append("     NEXT DAY after this regime was detected?")
    lines.append("  - 'Win rate' = out of all days in this regime, how often did")
    lines.append("     SPY close HIGHER the next day? (50% = coin flip)")
    lines.append("  - Higher win rate + positive returns = regime is good for trading")
    lines.append("  - Lower win rate + negative returns = danger zone")
    lines.append("")

    for _, row in stats_df.iterrows():
        r = row["regime"]
        n = int(row["count"])
        lines.append(f"{'='*70}")
        lines.append(f"REGIME {r} — {REGIME_NAMES.get(r,'?')}   (current flag: {FLAG_NAMES.get(r,'?')})")
        lines.append(f"{'='*70}")

        if n == 0:
            lines.append(f"  ⚠️  NEVER OCCURRED in {len(df)} trading days — threshold unreachable!")
            lines.append("")
            continue

        lines.append(f"  How often it happened: {n} days ({row['pct']}% of all trading days)")
        lines.append(f"  Average VIX when active: {row['avg_vix']}")
        lines.append(f"  Average SPY trend score: {row['avg_trend']} / 3")
        lines.append(f"  Average IWM/SPY ratio: {row['avg_iwm_rs']} (typical: ~0.37)")
        lines.append("")
        lines.append("  WHAT HAPPENED AFTER:")
        lines.append(f"  - Next day SPY avg return:  {row['avg_ret_1d']:+.3f}%")
        lines.append(f"  - Next 5 days SPY return:   {row['avg_ret_5d']:+.3f}%")
        lines.append(f"  - Next 21 days SPY return:  {row['avg_ret_21d']:+.3f}%")
        lines.append(f"  - Win rate (SPY up next day): {row['win_rate_1d']}%")
        lines.append("")

        # Simple verdict
        wr = row["win_rate_1d"]
        ret = row["avg_ret_1d"]
        if wr >= 58 and ret > 0.1:
            verdict = "✅ CONFIRMED BULLISH — regime flag seems correct"
        elif wr >= 53 and ret > 0:
            verdict = "✅ MILDLY BULLISH — regime flag seems OK"
        elif wr >= 47 and abs(ret) < 0.05:
            verdict = "😐 NEUTRAL — market goes sideways in this regime"
        elif wr < 47 or ret < -0.05:
            verdict = "⚠️  BEARISH/DANGEROUS — regime correctly signals caution"
        else:
            verdict = "❓ MIXED SIGNALS — needs more analysis"

        lines.append(f"  VERDICT: {verdict}")
        lines.append("")

    # Summary: does the flag system work?
    lines.append("=" * 70)
    lines.append("OVERALL VERDICT: DOES THE ARM FLAG SYSTEM WORK?")
    lines.append("=" * 70)

    risk_on_regimes = stats_df[stats_df["regime"].isin(["R0", "R1", "R1.5"])]
    caution_regimes = stats_df[stats_df["regime"].isin(["R2", "R4", "R5"])]
    risk_off_regimes = stats_df[stats_df["regime"].isin(["R3"])]

    def avg_metric(sub, col):
        sub = sub[sub["count"] > 0]
        if len(sub) == 0:
            return None
        return round((sub[col] * sub["count"]).sum() / sub["count"].sum(), 3)

    ro_wr = avg_metric(risk_on_regimes, "win_rate_1d")
    ca_wr = avg_metric(caution_regimes, "win_rate_1d")
    off_wr = avg_metric(risk_off_regimes, "win_rate_1d")

    lines.append("")
    lines.append("If the flag system is correct, we expect:")
    lines.append("  risk_on regimes → highest win rate (market goes up most)")
    lines.append("  caution regimes → medium win rate")
    lines.append("  risk_off regimes → lowest win rate (market struggles)")
    lines.append("")
    lines.append(f"  risk_on (R0/R1/R1.5) avg win rate: {ro_wr}%  (higher = better)")
    lines.append(f"  caution (R2) avg win rate:          {ca_wr}%  (should be middle)")
    lines.append(f"  risk_off (R3) avg win rate:         {off_wr}%  (lower = correct)")
    lines.append("")

    if ro_wr and ca_wr and off_wr:
        if ro_wr > ca_wr > off_wr:
            lines.append("  ✅ FLAG ORDERING IS CORRECT (risk_on > caution > risk_off)")
        elif ro_wr > off_wr:
            lines.append("  🟡 PARTIALLY CORRECT (risk_on beats risk_off, caution misplaced)")
        else:
            lines.append("  ❌ FLAG SYSTEM NEEDS REWORK (ordering does not match reality)")

    lines.append("")
    lines.append("NOTE: R4 = Volatile Trend (caution flag). R5 = Early Recovery (caution flag).")
    lines.append("  R4+R5: Bull Put allowed but RF filter decides. Future: backtest higher RF threshold.")

    lines.append("")
    lines.append(f"Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)

    with open(out_path, "w") as f:
        f.write("\n".join(lines))

    return "\n".join(lines)

# ========================
# MAIN
# ========================
def main():
    print("Fetching SPY, IWM, ^VIX from Yahoo Finance...")
    spy = fetch("SPY", START_DATE, END_DATE)
    iwm = fetch("IWM", START_DATE, END_DATE)
    vix = fetch("^VIX", START_DATE, END_DATE)
    print(f"  SPY: {len(spy)} days | IWM: {len(iwm)} days | VIX: {len(vix)} days")

    print("Computing ARM regime for every trading day...")
    df = build_regime_series(spy, iwm, vix)
    print(f"  Built {len(df)} regime rows")

    print("Adding forward returns...")
    df = add_forward_returns(df, spy)

    print("Saving historical CSV...")
    df.to_csv(CSV_OUT)
    print(f"  -> {CSV_OUT}")

    print("Computing per-regime statistics...")
    stats = regime_stats(df)
    print(stats.to_string())

    print("\nWriting plain-English report...")
    report = write_report(stats, df, REPORT_OUT)
    print(f"  -> {REPORT_OUT}")
    print()
    print(report)

if __name__ == "__main__":
    main()
