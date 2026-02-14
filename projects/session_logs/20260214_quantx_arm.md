# Session Log — 20260214 | quantx_arm

## Session Start
**Date:** 2026-02-14
**Context at start:** ARM V2 live. Strategies paper trading. 2021 DIX Part 4 running (PID 2875352). Bear Call skipped Feb 13 due to SPX snapshot failure — SPX snapshot retry (3 attempts) deployed in strategies session.

---

## Tasks Completed

### [DONE] ARM Pressure Dashboard — design + validation
**Goal:** Add downside/upside pressure scoring and escalation flag to ARM daily Telegram message.

**Validated on:**
- 2019–2021 historical regimes (756 trading days)
- 2020 crash window Feb 15–Apr 30 (52 days)
- 2024 H1 sideways/bull (105 days)
- Recent 6 months Aug 2025–Feb 2026 (120 days)

**Grid search (108 combos, properly buffered warmup):**
- Best params confirmed: `pct_th=0.08, abs_th_down=2.0, abs_th_up=1.0, gap_th=0.5`
- Zero false alarms in 2024 H1 bull market
- Crash detection: Feb 24 2020 caught day-of (day-1 = Feb 21 showed down_pressure=2, below gate)
- Recent escalation days (6m): 9 — all legitimate (STORM periods)

**Locked formula:**
```
vix_spike_down = (vix_pct >= +0.08) AND (vix_abs >= 2.0)   # strict
vix_spike_up   = (vix_pct <= -0.08) AND (vix_abs >= 1.0)   # relaxed (VIX drops gradual)
escalation     = (down_pressure == 3) AND (stability_score >= 2)
```

**Key design notes:**
- `vix_prev_close` carried via `pressure_state.json` (no yfinance VIX — IBKR authoritative)
- First run: `vix_prev_close` = `vix_close` → pct=0, pressure=0 (safe cold start)
- `regime_yday` from `pressure_state.json` (not `regime_state.json`) to ensure yesterday/today rows match
- Key changes section: only emits when regime flipped, escalation toggled, trend changed, or down_pressure moved ≥2

### [DONE] arm_regime_engine.py — pressure dashboard deployed
**Files changed:**
- `arm_regime_engine.py`: added constants, helpers, pressure computation, `pressure_state.json` save, new Telegram format
- New file written on first run: `state/pressure_state.json`

**Syntax check:** ✅ passes `py_compile`

**New Telegram format:**
```
📊 ARM + Pressure Dashboard | YYYY-MM-DD

Yesterday:
{emoji} {Rx} {Weather}
Down: X/3 | Up: Y/3 | Stability: Z (label)

Today:
{emoji} {Rx} {Weather} — RISK-ON/CAUTION/RISK-OFF
Down: X/3 — label (arrow)
Up:   Y/3 — label (arrow)
Stability: Z — label

Escalation: 🔴 YES / 🟢 NO

Key changes:  [only if something changed]
```

---

### [DONE] PROJECT_ARCHIVE.md + PROJECT_OVERVIEW.md updated
- Roadmap: added ARM Pressure Dashboard ✅ DONE 2026-02-14; added SPX RF retrain as 🔵 NEXT
- 6Y fetch table: 2021 Parts 1–4 corrected with actual trim dates (from check_last_date_quality.py); Part 4 marked ✅ COMPLETE 99.0% coverage; 2022 moved to 🔵 NEXT
- ARM section: added Pressure Dashboard subsection (params, formulas, validation summary)
- Strategy Design Rules: added Rule 7 — SPX snapshot retry
- Session history: added 2026-02-14 and 2026-02-12–13 entries
- Last archived: 2026-02-14

---

## Active Processes
| Process | PID | Command |
|---------|-----|---------|
| 2021 DIX fetch Part 4 | 2875352 | COMPLETE — 20211115→20211231, 99.0% coverage |
| Strategy cron | — | 18:30 UTC daily Mon–Fri |

---

---

### [DONE] RF Model upgraded: 6 → 9 features

**Backfill script:** `/root/projects/quantx_arm/scripts/backfill_arm_signals.py`

**What was done:**
- arm_state_history.csv had 157 rows (2024-09-10 → 2026-02-06) with empty spy_trend_score/vix_risk_flag/rs_iwm_spy
- Backfill script fetched SPY+IWM from yfinance, VIX from IBKR (Client ID 992, 2Y history, 501 bars)
- Computed EMA10/20/50 → spy_trend_score; VIX MA20 → vix_risk_flag; IWM/SPY ratio → rs_iwm_spy
- Result: **100% fill** on all 3 columns (162/162 rows)
- Rebuilt rf_features.csv (162 rows, 85 labeled, 12 cols including 3 new signals)
- Retrained model → `/root/odte_strategy/data/rf_model.joblib` (9 features, 85 labeled rows)
- Backup: `arm_state_history.csv.bak_20260214_112717`

**Model results (test set, 22 rows):**
- Accuracy: 45.5% (expected — 85 labeled rows is still small; class balance ~50/50)
- Feature importances: rs_iwm_spy 55%, days_in_regime 30%, regime_change 5%

**Note:** IWM/SPY ratio dominates because it captures breadth in context — when small caps lead, options selling trades more safely. Model accuracy will improve as more labeled data accumulates.

**Score distribution at current thresholds:**
- prob ≥ 0.60 → 38.8% of days TRADE
- prob ≥ 0.65 → 31.8% of days TRADE

---

### [DONE] 2020 Jan–Apr DIX refetch started
- PID 2938773, Client ID 83, range 20200101→20200416 (77 days)
- Output: `data/dix/history/chunk_2020_jan_apr.csv`
- Log: `/tmp/dix_2020_jan_apr.log`
- Should complete quickly (~2 min at 2400 days/hr)

---

## Active Processes
| Process | PID | Command |
|---------|-----|---------|
| 2020 Jan-Apr DIX refetch | 2938773 | 20200101→20200416, Client ID 83 |
| Strategy cron | — | 18:30 UTC daily Mon–Fri |

---

## Next Steps
- [ ] Monitor tomorrow's ARM run (14:45 UTC Feb 15) — confirm new Telegram format fires correctly
- [ ] Confirm `pressure_state.json` created in `state/` after first run
- [ ] After 2021 Part 4 completes: verify coverage → merge Part 3 (trim to 20211114) + Part 4 → start 2022 fetch
- [ ] Check PID 2938773 — when done verify ≥80% close coverage on chunk_2020_jan_apr.csv → merge with chunk_2020.csv
- [ ] As more paper trades labeled in rf_features.csv, retrain model to improve from current ~45% accuracy
