# ARM (Adaptive Regime Model) — Complete Reference

**Version:** V2 (deployed 2026-02-08)
**Last Updated:** 2026-02-08
**Source File:** `/root/projects/quantx_arm/arm_regime_engine.py`
**Config:** `/root/projects/quantx_arm/config/regime_rules_v1.json`
**Strategy Blocks:** `/root/projects/quantx_arm/config/strategy_blocks.json`
**State Output:** `/root/projects/quantx_arm/state/regime_state.json`

> ⚠️ **DO NOT DELETE THIS FILE OR SHORTEN SECTIONS** — This is the master reference for ARM regime system.
> Any change to ARM regime logic, thresholds, or flags MUST be documented here.

---

## 1. Purpose

ARM runs once per day (10:45 PM SGT / 14:45 UTC via `arm-rf-update.timer`) to classify the current market into one of 7 regime buckets (R0–R5, including R1.5). This regime label is then used by trading strategies to:
- Gate entries (skip trades in hostile regimes)
- Filter risk (e.g., Bull Put blocked in R3/STORM)
- Feed the RF (Risk Filter) score pipeline

---

## 2. Input Signals (3 Components)

| Signal | Symbol | Calculation | Range |
|--------|--------|-------------|-------|
| `spy_trend_score` | SPY | Count of EMAs (10, 20, 50 day) where SPY Close > EMA | 0 to 3 |
| `iwm_spy_rs` | IWM/SPY | `IWM_close / SPY_close` (ratio) | ~0.35–0.50 typical |
| `vix_risk_flag` | VIX | 1 if `VIX_close > VIX_20MA`, else 0 | 0 or 1 |

### Signal Details

**SPY Trend Score (0–3):**
- Score 3 = SPY above all 3 EMAs → strong uptrend
- Score 2 = SPY above 2 of 3 EMAs → moderate uptrend
- Score 1 = SPY above 1 of 3 EMAs → weak/mixed (early recovery territory)
- Score 0 = SPY below all EMAs → downtrend

**IWM/SPY Ratio (small-cap participation):**
- Higher ratio = small caps keeping up with large caps (broad market participation)
- Typical range: ~0.37–0.50 (IWM ~$200, SPY ~$540)
- **V2 Thresholds:** ≥0.45 for R0 (perfect bull), ≥0.40 for R1 (strong bull)
- Note: V1 thresholds (0.95/0.90) were unreachable — fixed in V2

**VIX Risk Flag:**
- Uses IBKR live VIX data (Client ID 991, fetches 1 month of daily bars)
- 1 = VIX elevated above its 20-day MA (fear/risk elevated)
- 0 = VIX below 20-day MA (calm market)
- VIX MA is a true 20-day rolling average computed from IBKR historical bars (fixed Feb 8, 2026)

---

## 3. Regime Classification Logic (V2 — Deployed)

Evaluated **in order** (first match wins — order matters!):

```python
if trend_score == 3 AND iwm_spy_rs >= 0.45 AND vix_risk == 0:  → R0   # Perfect bull
elif trend_score >= 2 AND iwm_spy_rs >= 0.40 AND vix_risk == 0: → R1   # Strong bull
elif trend_score >= 2 AND vix_risk == 0:                          → R1.5 # Moderate bull
elif trend_score == 1 AND vix_risk == 0:                          → R5   # Early recovery
elif trend_score == 0 AND vix_risk == 0:                          → R2   # Oversold bounce
elif trend_score == 0 AND vix_risk == 1:                          → R3   # Risk-off / Storm
elif trend_score >= 1 AND vix_risk == 1:                          → R4   # Volatile trend
else:                                                              → R5   # fallback (should never trigger)
```

All conditions are **mutually exclusive** — each market state maps to exactly one regime.

### V2 Changes from V1
| Change | V1 | V2 |
|--------|----|----|
| R0 IWM threshold | 0.95 (unreachable) | **0.45** |
| R1 IWM threshold | 0.90 (unreachable) | **0.40** |
| R5 definition | fallback catch-all | **early recovery** (trend=1, calm VIX) |
| R3 condition | trend≤1 (caught trend=1 days) | **trend=0 only** (pure breakdown) |
| R4 flag | none (bug) | **caution** |
| R1.5 flag | caution | **risk_on** |

---

## 4. Regime Stages — Full Breakdown (V2 — Backtested)

### Weather Display Names (shown in Telegram + reports)

| Code | Weather | Emoji | Order | Flag | Win Rate | % of Time | Avg VIX |
|------|---------|-------|-------|------|----------|-----------|---------|
| **R0** | **CLEAR** | ☀️ | 1 (best) | risk_on | 54.1% | 21.5% | 20.6 |
| **R1** | **SUNNY** | 🌤️ | 2 | risk_on | 54.9% | 12.6% | 19.9 |
| **R1.5** | **FAIR** | 🌥️ | 3 | risk_on | 60.1% | 17.8% | 15.7 |
| **R5** | **HAZE** | 🌫️ | 4 | caution | 52.4% | 2.7% | 22.9 |
| **R2** | **OVERCAST** | ☁️ | 5 | caution | 60.0% | 3.3% | 25.0 |
| **R4** | **GUSTY** | 💨 | 6 | caution | 54.1% | 26.7% | 20.3 |
| **R3** | **STORM** | ⛈️ | 7 (worst) | risk_off | 51.7% | 15.4% | 28.3 |

**Sequence logic:** Market travels the weather scale — CLEAR ↔ SUNNY ↔ FAIR ↔ HAZE ↔ OVERCAST ↔ GUSTY ↔ STORM

### Flags (V2 — Verified by Backtest)
```
risk_on  = CLEAR, SUNNY, FAIR  → avg 56.4% win rate — trade freely
caution  = HAZE, OVERCAST, GUSTY → avg 54.5% win rate — RF filter decides
risk_off = STORM               → 51.7% win rate — Bull Put blocked
```
✅ Ordering confirmed: risk_on > caution > risk_off (matches reality)

---

## 5. Trading Implications Per Regime (Plain English)

### ☀️ R0 / CLEAR — Perfect Bull
**What it means:** Everything is great. SPY is above ALL 3 EMAs, small caps (IWM) are keeping up with big caps (ratio ≥0.45), VIX is calm. Like a sunny summer day at the beach — no clouds, no wind.
- **Bear Call:** ✅ Trade normally (RF applies)
- **Bull Put:** ✅ Trade normally
- **What to do:** Trade full size, market is cooperating. Don't overthink it.
- **When this happens:** 21.5% of trading days

### 🌤️ R1 / SUNNY — Strong Bull
**What it means:** SPY is trending well, small caps have decent participation (ratio ≥0.40), VIX calm. Like a nice sunny day — maybe a few clouds but still great weather.
- **Bear Call:** ✅ Trade normally (RF applies)
- **Bull Put:** ✅ Trade normally
- **What to do:** Same as CLEAR. Conditions are good.
- **When this happens:** 12.6% of trading days

### 🌥️ R1.5 / FAIR — Mild Bull (Large Caps Leading)
**What it means:** SPY is trending but small caps are lagging behind. Big companies are doing well but smaller ones are not joining the party yet. VIX is calm. Like a fair weather day — still pleasant but not perfect.
- **Bear Call:** ✅ Trade normally (RF applies)
- **Bull Put:** ✅ Trade normally
- **What to do:** Trade normally. Note: this actually has the HIGHEST win rate (60.1%) because VIX is at its calmest here (~15.7). Don't be fooled by the "mild" label — this is a great trading environment.
- **When this happens:** 17.8% of trading days (very common)

### 🌫️ R5 / HAZE — Early Recovery (Green Shoot)
**What it means:** The market just started showing a tiny bit of life — SPY crossed above its shortest EMA (10-day) for the first time. Like that first peek of sun after days of rain. Looks hopeful but you're not sure yet.
- **Bear Call:** ✅ Allowed (RF applies)
- **Bull Put:** ❌ **BLOCKED — stress test showed 9.5% full-loss days (same as R3 risk level)**
- **What to do:** Do NOT sell Bull Put. R5 has a negative mean 1-day return (-0.147%) and 85.7% of R5 regimes last only 1 day — it frequently transitions directly to R3 (STORM). Too dangerous for put spreads.
- **Win rate is only 52%** — barely better than a coin flip.
- **When this happens:** 2.7% of trading days (rare)
- **Blocked since:** Feb 8, 2026 (stress test evidence)

### ☁️ R2 / OVERCAST — Oversold Bounce
**What it means:** SPY is below ALL EMAs (no trend) but VIX is calm. Market went down but nobody is panicking. Like a cloudy day — grey and flat but no storm.
- **Bear Call:** ✅ Allowed (RF applies)
- **Bull Put:** ✅ Allowed (RF decides)
- **What to do:** Interesting regime! Win rate is actually 60% and next-day avg is +0.503% — market tends to BOUNCE here because it's oversold but fear is low. Think of it like a bouncy ball hitting the floor — tends to come back up.
- **Important:** VIX is ~25 here — premiums are fatter but spreads can get tested intraday. RF filter matters.
- **When this happens:** 3.3% of trading days (rare)

### 💨 R4 / GUSTY — Volatile Trend (Choppy)
**What it means:** Market is still going up (SPY above at least 1 EMA) BUT VIX is elevated. Like a gusty windy day — you can still go outside but it's messy. Things are moving but unpredictably.
- **Bear Call:** ✅ Allowed (RF applies)
- **Bull Put:** ✅ Allowed (RF decides — be selective)
- **What to do:** Market is trending but choppy. Option premiums are richer due to higher VIX, which sounds good for selling — but intraday swings can hit your strikes. RF filter is your shield here.
- **Win rate is 54%** — decent but not great. Let RF decide.
- **When this happens:** 26.7% of trading days — the MOST COMMON regime!
- **Future TODO (Aug 2026):** Backtest optimal RF threshold for Bull Put in GUSTY

### ⛈️ R3 / STORM — Market Breakdown
**What it means:** SPY is below ALL EMAs (no trend at all — score=0) AND VIX is spiking above its average. The market is in pure fear mode. Like a thunderstorm — stay inside.
- **Bear Call:** ✅ Allowed (RF applies — bearish market = Bear Call could work)
- **Bull Put:** ❌ **BLOCKED — do not sell put spreads**
- **What to do:** Do NOT sell Bull Put spreads. VIX is ~28+ meaning the market swings wildly. Even if SPY closes flat, it could tag your put strike intraday and you'd lose. Wait for weather to improve to at least GUSTY before resuming Bull Put.
- **Win rate is 51.7%** — worst of all regimes (barely above coin flip)
- **When this happens:** 15.4% of trading days

---

## 6. Strategy Gate Summary

| Strategy | Gate Condition | Effect |
|----------|---------------|--------|
| Bull Put (002) | `regime in ["R3", "R5"]` | Skip entire strategy, no trade |
| Bear Call (001) | No ARM gate | RF_THRESHOLD applies instead |

The Bull Put strategy (002) directly reads `regime_state.json` and exits if regime is R3/STORM or R5/HAZE.
R5 blocked since Feb 8, 2026 — stress test showed 9.5% full-loss days (same risk level as R3).

---

## 7. Data Flow & Update Schedule

```
Daily at 14:45 UTC (10:45 PM SGT):
  1. arm_regime_engine.py  → writes regime_state.json
  2. arm_history_append.py → appends to /root/odte_strategy/data/arm_state_history.csv
  3. rf_score_daily.py     → recalculates RF scores per ticker
```

### VIX Handling
- VIX is fetched from IBKR (Client ID 991, port 4002) — requests 1 month of daily bars
- **VIX MA is a true 20-day rolling average** computed from those IBKR bars (fixed Feb 8, 2026)
- If IBKR fetch fails, system falls back to previous state values (clearly marked as degraded)
- If no previous state exists, defaults vix_close=0, vix_ma=0 (biases toward risk_on — degraded flag set)

---

## 8. Backtest Results (V2 — 2020-01-01 to 2026-02-08, 1,533 trading days)

**Script:** `/root/odte_strategy/data/backtest_results/arm_regime_backtest.py`
**Full data:** `/root/odte_strategy/data/backtest_results/arm_regime_historical.csv`
**Full report:** `/root/odte_strategy/data/backtest_results/arm_regime_stats_report.txt`

### V2 Results Table

| Regime | Days | % of Time | Next Day Avg | 5-Day Avg | 21-Day Avg | Win Rate | Avg VIX | Verdict |
|--------|------|-----------|-------------|-----------|-----------|----------|---------|---------|
| R0 CLEAR | 329 | 21.5% | +0.039% | +0.240% | +0.274% | 54.1% | 20.6 | ✅ Mildly bullish |
| R1 SUNNY | 193 | 12.6% | +0.118% | +0.377% | +1.758% | 54.9% | 19.9 | ✅ Mildly bullish |
| R1.5 FAIR | 273 | 17.8% | +0.083% | +0.323% | +1.516% | **60.1%** | **15.7** | ✅ Best win rate |
| R5 HAZE | 42 | 2.7% | -0.147% | +0.626% | +1.939% | 52.4% | 22.9 | ⚠️ Caution — setup for recovery |
| R2 OVERCAST | 50 | 3.3% | **+0.503%** | **+1.748%** | **+3.366%** | 60.0% | 25.0 | ✅ Bounce signal |
| R4 GUSTY | 410 | 26.7% | +0.014% | +0.087% | +1.241% | 54.1% | 20.3 | 😐 Neutral / choppy |
| R3 STORM | 236 | 15.4% | +0.059% | +0.365% | +1.707% | 51.7% | **28.3** | ⚠️ Worst win rate |

### Key Findings (Plain English)

**Finding 1: Flag ordering is CONFIRMED correct.**
risk_on (R0/R1/R1.5) → 56.4% avg win rate
caution (R2/R4/R5) → 54.5% avg win rate
risk_off (R3) → 51.7% win rate
✅ Each tier performs as expected — the system works.

**Finding 2: R1.5 (FAIR) has the highest win rate at 60.1%.**
Why? VIX is at its calmest (avg 15.7). When large caps are trending and VIX is low, option selling is optimal. Don't let the "mild" label fool you — this is actually the best environment.

**Finding 3: R2 (OVERCAST) is a strong bounce signal.**
SPY below all EMAs but VIX calm = oversold, no panic. Markets tend to bounce (+0.503% avg next day, +3.366% avg over 21 days). This is mean reversion at work. VIX is ~25 though, so fat premiums BUT also fat intraday swings.

**Finding 4: R3 (STORM) Bull Put block is CORRECT even though returns look slightly positive.**
Win rate 51.7% and VIX avg 28.3. When VIX=28, selling put spreads is dangerous because intraday swings can blow through strikes even if market closes flat. The block stays.

**Finding 5: R5 (HAZE) next-day return is slightly negative (-0.147%) but 5-day and 21-day are positive.**
This is a setup/transition regime — the first day of recovery is often shaky. It's a green shoot, not a full bloom. Use RF filter to avoid trading on the worst HAZE days.

**Finding 6: R4 (GUSTY) is the most common regime at 26.7% of days.**
High VIX + trending = choppy intraday. Win rate (54.1%) is decent but the RF filter is essential here to avoid days where VIX spikes and smashes your put strikes.

### Overall Verdict
✅ **FLAG ORDERING IS CORRECT** — risk_on beats caution beats risk_off as expected.
The ARM V2 system is validated. The weather naming matches the market reality.

---

## 9. Resolved Issues (All Fixed in V2)

All the following bugs existed in V1 and have been fixed in V2 (deployed 2026-02-08):

| Issue | V1 Problem | V2 Fix |
|-------|-----------|--------|
| R0/R1 never occurred | IWM thresholds 0.95/0.90 unreachable | Fixed to 0.45/0.40 |
| R3 captured trend=1 days | Condition was `trend≤1` | Fixed to `trend==0` only |
| R4 had no flag | All three flags = 0 (bug) | Fixed: R4 = caution |
| R1.5 was "caution" | Despite 56%+ win rate in bull market | Fixed: R1.5 = risk_on |
| R5 was an unreachable catch-all | `else` clause that never triggered | Fixed: R5 = early recovery (trend=1, calm VIX) |
| Duplicate Telegram notification | Message sent twice per update | Fixed: removed duplicate block |
| Overlapping conditions (R1.5/R2) | Both could match trend=1 days | Fixed: all regimes mutually exclusive |
| VIX MA was stale carry-forward | Just copied yesterday's JSON vix_ma | Fixed: true 20-day rolling MA from 1-month IBKR bars |

---

## 10. Current State (as of 2026-02-08)

```json
{
  "regime": "R4",
  "regime_display": "GUSTY",
  "regime_desc": "Volatile trend — moving but bumpy, RF filter on",
  "scores": {
    "spy_trend_score": 1,
    "iwm_spy_rs": 0.382,
    "vix_risk_flag": 1
  },
  "flags": {
    "risk_off": 0,
    "caution": 1,
    "risk_on": 0
  },
  "blocked_strategies_today": []
}
```

**Interpretation (V2):** SPY above 1 EMA but VIX elevated → GUSTY (volatile trend). Caution flag active. Bull Put is allowed but RF filter decides.

Note: Under V1, this same state would have incorrectly shown as R3 (because R3 condition was `trend≤1 AND vix=1`, which captured trend=1). Under V2, trend=1 + vix=1 correctly goes to R4 (GUSTY), not R3 (STORM).

---

## 11. Future TODO (Before Aug 2026)

| Task | Status | Description |
|------|--------|-------------|
| R4/R5 Bull Put higher RF threshold | 🔴 NOT STARTED | Backtest optimal RF threshold for Bull Put in GUSTY and HAZE regimes |

---

## 12. File Reference

| File | Purpose |
|------|---------|
| `arm_regime_engine.py` | Main engine — runs daily, writes state |
| `ib_vix.py` | VIX fetcher from IBKR |
| `config/regime_rules_v1.json` | EMA periods (10,20,50), VIX MA period (20), IWM thresholds |
| `config/strategy_blocks.json` | Which strategies blocked in which regime |
| `state/regime_state.json` | Today's regime output (read by strategies) |
| `/root/odte_strategy/data/arm_state_history.csv` | Historical regime log |
| `/root/odte_strategy/scripts/arm_history_append.py` | Appends daily state to history |
| `/root/odte_strategy/scripts/rf_score_daily.py` | RF score calculation using ARM history |
| `/root/odte_strategy/data/backtest_results/arm_regime_backtest.py` | V2 backtest script |
| `/root/odte_strategy/data/backtest_results/arm_regime_historical.csv` | 1,533 days of regime labels |
| `/root/odte_strategy/data/backtest_results/arm_regime_stats_report.txt` | V2 backtest report |
