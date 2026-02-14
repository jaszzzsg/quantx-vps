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
- [ ] As more paper trades fire and are labeled, retrain model. Target ~150 labeled rows before trusting forward AUC

---

### [DONE] RF label logic improved: removed noisy d_close < entry_px

**File changed:** `/root/odte_strategy/data/rf_build_features.py`

**Problem:** Old label marked BAD if `d_close < entry_px` — 174/339 traded days flagged. This is noisy because SPX closing slightly below the short put strike ≠ actual loss.

**New logic (BAD=0):**
- `breach==1 OR full_loss==1` — real structural events
- `spy_dd_next <= DD_THRESH (-0.007)` — next-trading-day SPY intraday drawdown > 0.7%

**Constant:** `DD_THRESH = -0.007` at top of rf_build_features.py (easy to tune)

**Label shift across all 339 outcomes:**
- Old BAD: 174 (51% — d_close < entry_px was dominant)
- New BAD: 83 total (breach/full_loss/dd combined) — 15 breach, 7 full_loss, 72 dd-triggered

**RF features row view (85 labeled, arm_state_history window 2024-09-10+):**
- Old: 45 BAD / 40 GOOD — bad_rate 52.9%
- New: 21 BAD / 64 GOOD — bad_rate 24.7%

**Model results (retrained 2026-02-14 11:50 UTC):**
- Accuracy: 77.3% (was 45.5%)
- **AUC: 0.935**
- Bad rate at threshold 0.65: **3.8%** vs baseline 24.7% — 6.5x lift
- Bad rate at threshold 0.60: **5.3%** vs baseline — 4.7x lift

**Feature importances:** rs_iwm_spy 57%, days_in_regime 31% (unchanged structure)

---

### [DONE] RF threshold set to 0.65 + time-based split validation

**Files changed:**
- `scripts/rf_score_daily.py`: Added `RF_TRADE_THRESH = 0.65` constant; per-regime `REGIME_THR` updated to use it as baseline; verbose scoring printout added
- `scripts/rf_time_split_validate.py`: New validation script (time-based 70/30 split, no shuffle)
- `.env.paper`: Kept at `RF_THR=0.10` — see note below

**Time-based forward validation results (train Sep 2024–May 2025, test May–Dec 2025):**
- Accuracy: 53.8%,  **AUC: 0.503** (vs random-split AUC 0.935)
- **Conclusion: random-split AUC was inflated by time-series data leakage**
- Forward-period BADs occur in R1.5 (fair regime) — model learned "R1.5 = safe" from training, fails on BAD days in R1.5 during test

**Why the model isn't ready for tight gating yet:**
- 85 labeled rows is too small; 26-row test set with 9 BADs is statistically fragile
- The ARM regime gate (R3/R5 blocks) is the primary protection; RF is supplementary
- Need ~150 labeled rows before forward AUC becomes reliable

**Decision on RF_THR:**
- `.env.paper` stays at `0.10` — low gate to keep paper trades firing and accumulating labeled data
- `RF_TRADE_THRESH = 0.65` is set in code as the activation threshold for live trading
- Will switch `.env.paper` to `0.65` (or remove `RF_THR` override) when transitioning to live

---

### [DONE] 3 shock features added + spy_dd_next sanity confirmed

**Files changed:**
- `scripts/backfill_arm_signals.py`: Added vix_close, vix_change_1d, spy_return_1d, spy_gap (SPY Open now downloaded)
- `scripts/arm_history_append.py`: Added daily collection of vix_close (from regime_state.json), vix_change_1d (diff vs prev row), spy_return_1d, spy_gap (from yfinance)
- `data/rf_build_features.py`: spy_dd_next sanity print added (verifies trading-day shift); new optional columns included
- `scripts/rf_train_once.py` + `rf_time_split_validate.py`: PREFERRED_COLS expanded to 12

**spy_dd_next sanity — confirmed correct:**
- Dec 15 (Friday) → Dec 18 (Monday): next_trade_date correctly skips weekend ✅
- Using positional shift(-1) on trading-day index, not calendar days

**New features (all 100% filled after backfill):**
- `vix_close`: raw IBKR VIX close
- `vix_change_1d`: VIX today minus VIX yesterday (shock signal)
- `spy_return_1d`: SPY close-to-close return
- `spy_gap`: SPY overnight gap (open / prev_close - 1)

**Model now 12 features (was 9):**

**Forward time-split AUC improvement:**
| Model | Random-split AUC | Forward AUC (70/30 time split) |
|---|---|---|
| 9 features (no shock) | 0.935 | 0.503 |
| 12 features (+ shock) | — | **0.680** |

Feature importance (12-feat): rs_iwm_spy 21%, spy_return_1d 19%, vix_change_1d 18%, days_in_regime 17%, spy_gap 17% — well distributed, no single dominant feature

**Threshold analysis (12-feat, test period May–Dec 2025):**
- thr=0.70: 76.9% trade rate, bad_rate=35.0% (≈ baseline 34.6%) — at 0.70 still near-random
- thr=0.65: bad_rate=40.9% — worse than baseline (model is not calibrated yet)
- **Conclusion:** Forward AUC 0.68 is a meaningful improvement but threshold gating still needs more data. ARM regime gate remains primary protection. Target 150 labeled rows.

**Next steps:**
- Continue paper trading with RF_THR=0.10
- Rerun rf_time_split_validate.py when 150+ labeled rows accumulate
