#!/usr/bin/env python3
"""
ARM Regime Stress Test
======================
Analyzes regime stability, boundary sensitivity, and tail risk
using 1,533 days of historical data (2020-2026).

Outputs:
- Regime transition matrix (stability)
- Boundary proximity (how often near threshold crossings)
- Tail risk per regime (breach-risk proxy)
- Consecutive run analysis
- Bull Put risk profile per regime
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATA_FILE = Path("/root/odte_strategy/data/backtest_results/arm_regime_historical.csv")
OUTPUT_FILE = Path("/root/odte_strategy/data/backtest_results/arm_regime_stress_report.txt")

WEATHER = {
    "R0": "☀️  CLEAR",
    "R1": "🌤️  SUNNY",
    "R1.5": "🌥️  FAIR",
    "R5": "🌫️  HAZE",
    "R2": "☁️  OVERCAST",
    "R3": "⛈️  STORM",
    "R4": "💨  GUSTY",
}

REGIME_ORDER = ["R0", "R1", "R1.5", "R5", "R2", "R3", "R4"]

# Bull Put breach proxy: SPX 1-day return threshold
BREACH_THRESHOLD = -1.5   # -1.5% daily move = likely Bull Put stress
FULL_LOSS_THRESHOLD = -3.0  # -3.0% = near full loss scenario


def run():
    df = pd.read_csv(DATA_FILE, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)

    lines = []
    def p(s=""):
        lines.append(s)

    p("=" * 70)
    p("ARM REGIME STRESS TEST REPORT")
    p(f"Data: {df['date'].iloc[0].date()} to {df['date'].iloc[-1].date()} ({len(df)} trading days)")
    p("=" * 70)

    # =========================================================
    # 1. REGIME DISTRIBUTION
    # =========================================================
    p()
    p("━" * 70)
    p("1. REGIME DISTRIBUTION")
    p("━" * 70)
    counts = df["regime"].value_counts()
    for r in REGIME_ORDER:
        n = counts.get(r, 0)
        pct = n / len(df) * 100
        bar = "█" * int(pct / 2)
        p(f"  {r:5s} {WEATHER.get(r, r):15s}  {n:4d} days ({pct:5.1f}%)  {bar}")

    # =========================================================
    # 2. REGIME TRANSITION MATRIX (stability)
    # =========================================================
    p()
    p("━" * 70)
    p("2. REGIME TRANSITION MATRIX (day N → day N+1)")
    p("   Diagonal = stayed in same regime (high = stable)")
    p("━" * 70)

    df["next_regime"] = df["regime"].shift(-1)
    transitions = df.dropna(subset=["next_regime"]).copy()

    trans_matrix = pd.crosstab(
        transitions["regime"],
        transitions["next_regime"],
        normalize="index"
    ) * 100
    # reindex to consistent order
    trans_matrix = trans_matrix.reindex(
        index=[r for r in REGIME_ORDER if r in trans_matrix.index],
        columns=[r for r in REGIME_ORDER if r in trans_matrix.columns],
        fill_value=0
    )

    # header
    header = f"  {'From→':8s}" + "".join(f"{c:7s}" for c in trans_matrix.columns)
    p(header)
    p("  " + "-" * (8 + 7 * len(trans_matrix.columns)))
    for r in trans_matrix.index:
        row = f"  {r:8s}"
        for c in trans_matrix.columns:
            val = trans_matrix.loc[r, c]
            marker = "◆" if r == c else " "
            row += f"{val:5.1f}%{marker} "
        p(row)

    p()
    p("  Stability scores (% staying in same regime next day):")
    for r in REGIME_ORDER:
        if r in trans_matrix.index and r in trans_matrix.columns:
            stay = trans_matrix.loc[r, r]
            stability = "STABLE" if stay >= 70 else ("MODERATE" if stay >= 50 else "UNSTABLE")
            p(f"    {r:5s} {WEATHER.get(r, r):15s}  {stay:5.1f}%  [{stability}]")

    # =========================================================
    # 3. BOUNDARY PROXIMITY (threshold sensitivity)
    # =========================================================
    p()
    p("━" * 70)
    p("3. BOUNDARY PROXIMITY (how often near threshold crossings)")
    p("━" * 70)

    # VIX proximity: |vix_close - vix_ma| < 0.5
    vix_diff = (df["vix_close"] - df["vix_ma"]).abs()
    near_vix = (vix_diff < 0.5).sum()
    very_near_vix = (vix_diff < 0.25).sum()
    p(f"  VIX / VIX-MA boundary (|vix - ma| < 0.5):  {near_vix:4d} days ({near_vix/len(df)*100:.1f}%)")
    p(f"  VIX / VIX-MA boundary (|vix - ma| < 0.25): {very_near_vix:4d} days ({very_near_vix/len(df)*100:.1f}%)")
    p(f"  → On these days, a ±0.5 VIX shift would flip vix_risk_flag")

    p()
    # IWM/SPY proximity for R0 threshold (0.45) and R1 threshold (0.40)
    rs = df["iwm_spy_rs"]
    near_r0 = ((rs - 0.45).abs() < 0.005).sum()
    near_r1 = ((rs - 0.40).abs() < 0.005).sum()
    p(f"  IWM/SPY near R0 threshold (|rs - 0.45| < 0.005): {near_r0:4d} days ({near_r0/len(df)*100:.1f}%)")
    p(f"  IWM/SPY near R1 threshold (|rs - 0.40| < 0.005): {near_r1:4d} days ({near_r1/len(df)*100:.1f}%)")

    p()
    # Regime boundary crossings per regime pair (most volatile transitions)
    p("  Most common regime transitions (instability signals):")
    cross_counts = transitions[transitions["regime"] != transitions["next_regime"]].groupby(
        ["regime", "next_regime"]
    ).size().sort_values(ascending=False).head(10)
    for (fr, to), cnt in cross_counts.items():
        p(f"    {fr:5s} → {to:5s}  {cnt:3d} times")

    # =========================================================
    # 4. TAIL RISK PER REGIME (Bull Put breach proxy)
    # =========================================================
    p()
    p("━" * 70)
    p("4. TAIL RISK PER REGIME (Bull Put breach proxy)")
    p(f"   Stress day = ret_1d < {BREACH_THRESHOLD}% | Full-loss day = ret_1d < {FULL_LOSS_THRESHOLD}%")
    p("━" * 70)

    header2 = f"  {'Regime':8s} {'Days':>6s} {'Mean%':>7s} {'Std%':>6s} {'Min%':>7s} {'Stress%':>8s} {'FullLoss%':>10s}"
    p(header2)
    p("  " + "-" * 55)
    for r in REGIME_ORDER:
        sub = df[df["regime"] == r]["ret_1d"]
        if len(sub) == 0:
            continue
        stress_pct = (sub < BREACH_THRESHOLD).sum() / len(sub) * 100
        full_loss_pct = (sub < FULL_LOSS_THRESHOLD).sum() / len(sub) * 100
        p(f"  {r:8s} {len(sub):6d} {sub.mean():7.3f} {sub.std():6.3f} {sub.min():7.3f} {stress_pct:8.1f}% {full_loss_pct:10.1f}%")

    p()
    p("  Interpretation:")
    p("  - Stress% = % of days where Bull Put would face significant pressure")
    p("  - FullLoss% = % of days approaching max loss scenario")
    p("  - Compare R4/R5 vs R0/R1 to quantify regime risk premium")

    # =========================================================
    # 5. CONSECUTIVE RUN ANALYSIS
    # =========================================================
    p()
    p("━" * 70)
    p("5. CONSECUTIVE RUN ANALYSIS (regime persistence)")
    p("━" * 70)

    runs = {}
    current_regime = None
    current_run = 0
    for regime in df["regime"]:
        if regime == current_regime:
            current_run += 1
        else:
            if current_regime:
                runs.setdefault(current_regime, []).append(current_run)
            current_regime = regime
            current_run = 1
    if current_regime:
        runs.setdefault(current_regime, []).append(current_run)

    p(f"  {'Regime':8s} {'Runs':>6s} {'AvgDays':>8s} {'MedianDays':>11s} {'MaxDays':>9s} {'1-day%':>8s}")
    p("  " + "-" * 54)
    for r in REGIME_ORDER:
        if r not in runs:
            continue
        r_runs = runs[r]
        avg = np.mean(r_runs)
        med = np.median(r_runs)
        mx = max(r_runs)
        one_day_pct = sum(1 for x in r_runs if x == 1) / len(r_runs) * 100
        p(f"  {r:8s} {len(r_runs):6d} {avg:8.1f} {med:11.1f} {mx:9d} {one_day_pct:8.1f}%")

    p()
    p("  1-day% = regimes that lasted only 1 day (noise/flickering indicator)")

    # =========================================================
    # 6. REGIME-SPECIFIC STRESS WINDOWS (worst episodes)
    # =========================================================
    p()
    p("━" * 70)
    p("6. WORST STRESS EPISODES PER REGIME (days with ret_1d < -2%)")
    p("━" * 70)

    for r in ["R4", "R5", "R2", "R3"]:
        worst = df[df["regime"] == r].nsmallest(5, "ret_1d")[["date", "ret_1d", "vix_close", "vix_ma", "spy_trend_score"]]
        p(f"\n  {r} {WEATHER.get(r, '')} — worst 5 days:")
        p(f"  {'Date':12s} {'ret_1d':>8s} {'VIX':>6s} {'VIX_MA':>8s} {'Trend':>6s}")
        for _, row in worst.iterrows():
            p(f"  {str(row['date'].date()):12s} {row['ret_1d']:8.2f}% {row['vix_close']:6.2f} {row['vix_ma']:8.2f} {int(row['spy_trend_score']):6d}")

    # =========================================================
    # 7. RF THRESHOLD PROXY ANALYSIS
    # =========================================================
    p()
    p("━" * 70)
    p("7. RF THRESHOLD PROXY: What % of R4/R5 bad days could RF filter catch?")
    p("   (Simulated: assume RF blocks bottom X% of days by some future signal)")
    p("━" * 70)

    for r in ["R4", "R5", "R2"]:
        sub = df[df["regime"] == r]["ret_1d"].sort_values()
        if len(sub) < 5:
            continue
        total = len(sub)
        stress_days = (sub < BREACH_THRESHOLD).sum()
        p(f"\n  {r} {WEATHER.get(r, '')} ({total} days, {stress_days} stress days):")
        p(f"  {'Block bottom N%':20s} {'Days blocked':>13s} {'Stress captured':>16s} {'Clean days lost':>16s}")
        for pct_block in [10, 15, 20, 25, 30]:
            n_block = int(total * pct_block / 100)
            blocked_set = set(sub.head(n_block).index)
            stress_captured = sum(1 for i in blocked_set if sub[i] < BREACH_THRESHOLD)
            clean_lost = n_block - stress_captured
            if stress_days > 0:
                capture_rate = stress_captured / stress_days * 100
                p(f"  {pct_block:3d}%                  {n_block:6d} days      {stress_captured:4d} ({capture_rate:4.0f}%)     {clean_lost:4d} ({clean_lost/total*100:4.0f}%)")

    p()
    p("  Note: This shows trade-off — blocking more days catches more stress but")
    p("  also skips profitable days. RF model should target >50% stress capture")
    p("  with <20% clean days lost.")

    # =========================================================
    # SUMMARY
    # =========================================================
    p()
    p("=" * 70)
    p("SUMMARY & KEY FINDINGS")
    p("=" * 70)

    # Find most unstable regimes
    unstable = []
    for r in REGIME_ORDER:
        if r in trans_matrix.index and r in trans_matrix.columns:
            stay = trans_matrix.loc[r, r]
            if stay < 60:
                unstable.append((r, stay))

    if unstable:
        p(f"  ⚠️  Unstable regimes (< 60% persistence): {', '.join(f'{r}({s:.0f}%)' for r,s in unstable)}")
    else:
        p("  ✅  All regimes have >60% day-to-day persistence")

    # R5 finding
    r5_stress = (df[df["regime"] == "R5"]["ret_1d"] < BREACH_THRESHOLD).sum()
    r5_total = (df["regime"] == "R5").sum()
    p(f"  ⚠️  R5 (HAZE): negative mean return ({df[df['regime']=='R5']['ret_1d'].mean():.3f}%) — early recovery is risky")
    p(f"      {r5_stress}/{r5_total} R5 days ({r5_stress/r5_total*100:.1f}%) had stress-level drops")

    r4_stress = (df[df["regime"] == "R4"]["ret_1d"] < BREACH_THRESHOLD).sum()
    r4_total = (df["regime"] == "R4").sum()
    p(f"  📊  R4 (GUSTY): {r4_stress}/{r4_total} R4 days ({r4_stress/r4_total*100:.1f}%) had stress-level drops")

    r0_stress = (df[df["regime"] == "R0"]["ret_1d"] < BREACH_THRESHOLD).sum()
    r0_total = (df["regime"] == "R0").sum()
    p(f"  ✅  R0 (CLEAR): {r0_stress}/{r0_total} R0 days ({r0_stress/r0_total*100:.1f}%) had stress-level drops (baseline)")

    p()
    p(f"  VIX boundary days (within ±0.5): {near_vix} ({near_vix/len(df)*100:.1f}%) — regime can flip on small VIX moves")
    p()
    p(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}")
    p("=" * 70)

    # Write to file and print
    report = "\n".join(lines)
    OUTPUT_FILE.write_text(report)
    print(report)
    print(f"\n✅ Report saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
