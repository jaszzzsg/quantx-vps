# QuantX Projects Overview
**For Claude AI Assistant — Read This First Every Session**

---

## Quick Start (Every Session)
1. Read this file
2. Read the latest session log: `ls -t /root/projects/session_logs/ | head -1` then read that file
3. Check any active PIDs from session log are still running
4. Ask user what to work on (or continue from session log's Next Steps)

## Session Log System
- **Location:** `/root/projects/session_logs/YYYYMMDD_<project>.md`
- **Naming:** `<project>` = the component being worked on that session:
  - `quantx_dix` — DIX pipeline work
  - `quantx_arm` — ARM regime work
  - `quantx_strategies` — 0DTE strategy work
  - `quantx_system` — cross-cutting (git, infra, multi-component)
  - Same day + same project = append to existing file
- **At session start:** run `ls -t /root/projects/session_logs/ | head -3` to see recent logs, read the most relevant one
- **During session:** update the log as each task completes (so crashes/context limits don't lose progress)
- **At session end (MANDATORY — both steps):**
  1. Mark all completed items, write Next Steps, note any active PIDs in session log
  2. `cd /root/projects && ./git-sync.sh "YYYYMMDD <project>: brief summary"` — push to GitHub (repo root is `/root/`)

---

## ⚠️ CRITICAL RULES (CANNOT BE DELETED)

### IBKR Concurrent Fetch Limitation
- Cannot fetch two historical date ranges simultaneously — gateway supports one at a time
- Always complete current chunk before starting next

### Mandatory Data Merge Rule
- **Minimum 80% close price coverage** before merging any files into production data
- Never merge low-quality data with high-quality data

### ARM Update Rule
- Any change to ARM regime logic, thresholds, or flags **MUST be documented in:**
  `/root/projects/quantx_arm/ARM_REGIME_REFERENCE.md`

### ⚠️ MANDATORY DATE FORMAT: YYYYMMDD (NO DASHES)
**ALL dates across QuantX** — CSV columns, filenames, IBKR args, backtest scripts — use `YYYYMMDD` (8-digit integer, no dashes).

| Context | ✅ Correct | ❌ Wrong |
|---------|-----------|---------|
| CSV date columns | `20260210` | `2026-02-10` |
| Pandas parse | `pd.to_datetime(df["date"].astype(str), format="%Y%m%d")` | `pd.to_datetime(df["date"])` — reads int as nanoseconds → `1970-01-01`! |
| IBKR args | `--start 20260210` | `--start 2026-02-10` |

### Haiku Double-Read Protocol
ONLY when running as Haiku (claude-haiku-4-5-20251001): read PROJECT_OVERVIEW.md twice before any user file.

---

## Current Status
*(Update this section each session)*

**As of 2026-02-14:**
- Paper trading ACTIVE — cron at 18:30 UTC (1:30 PM ET) weekdays, account DUP148773
- RF_THRESHOLD = 0.65 (set 2026-02-14 — trial mode ended; random-split AUC 0.935, but forward AUC ~0.5 — ARM gate is primary protection)
- Strategy fix deployed (2026-02-12): leg-based mid pricing replaces Bag streaming — first live test NOT YET CONFIRMED (Bear Call skipped Feb 13 due to SPX snapshot NaN — retry fix deployed Feb 14)
- ARM Pressure Dashboard deployed (2026-02-14) — new Telegram format with down/up/stability/escalation scores; first live fire at 14:45 UTC Feb 15
- 2021 DIX fetch Part 4: COMPLETE (PID 2875352 finished) — full 2021 year covered (Parts 1–4), merge pending

## Known Issues
- `rf_daily_predictions.csv` has junk row with date `19700101` (epoch artifact) — cosmetic only, upsert deduplicates
- 2021 DIX fetch script uses `open("w")` — if it dies, must restart from day 1, never resume mid-file
- **IBKR Bag/combo `reqMktData` does NOT return bid/ask for SPX spreads** — always use leg-based snapshot pricing for any new option spread strategy (fix deployed 2026-02-12, pending first confirmed trade)

---

## System Architecture

### Project Paths
| Component | Root Path |
|-----------|-----------|
| DIX pipeline | `/root/projects/quantx_dix/` |
| ARM regime | `/root/projects/quantx_arm/` |
| Trading strategies | `/root/projects/QuantX_Dashboard_Monitor-main/` |
| IBKR client IDs | `/root/shared/ibkr/CLIENT_ID_REGISTRY.md` |
| odte strategy data | `/root/odte_strategy/` |
| Session logs | `/root/projects/session_logs/` |
| Archive | `/root/projects/PROJECT_ARCHIVE.md` |

### Key Files
| File | Purpose |
|------|---------|
| `quantx_arm/arm_regime_engine.py` | ARM regime update |
| `quantx_arm/state/regime_state.json` | Current regime state |
| `quantx_arm/ARM_REGIME_REFERENCE.md` | ARM regime reference (single source of truth) |
| `odte_strategy/data/rf_daily_predictions.csv` | RF scores (YYYYMMDD dates) |
| `odte_strategy/scripts/rf_score_daily.py` | Daily RF scoring |
| `odte_strategy/.env.paper` | Strategy env vars (RF_THR, TG tokens) — NO inline `#` comments on value lines! |
| `strategies_runner/001_alpha_spx_1330_0dte_bear_call.py` | Bear Call strategy |
| `strategies_runner/002_alpha_spx_1330_0dte_bull_put.py` | Bull Put strategy |
| `run_1330_strategies.sh` | Cron wrapper for both strategies |

### IBKR Connections
| Port | Type | Client IDs in use |
|------|------|-------------------|
| 4001 | LIVE | — |
| 4002 | PAPER | 22 (DIX daily), 83 (6Y fetch active), 991 (ARM VIX) |

**Client ID registry:** `/root/shared/ibkr/CLIENT_ID_REGISTRY.md` — check before assigning any new ID.
**Reuse rule:** An ID is free as soon as its PID is dead. Run `ps -p <PID>` to confirm, then reuse the same ID. Only increment if the process is still alive.

### Scheduled Timers
| Timer | Schedule | Purpose |
|-------|----------|---------|
| `arm-rf-update.timer` | 14:45 UTC daily | ARM regime → arm_history_append → rf_score_daily |
| `quantx-dix-daily.timer` | 01:00 UTC daily | DIX fetch |
| `quantx-dix-precious-metals.timer` | 01:30 UTC daily | Precious metals Telegram |
| `rf-train-score.timer` | Saturday 10:00 AM ET | RF model retrain |
| `quantx-dix-history-update.timer` | Saturday 00:30 UTC | Merge daily → master |
| `quantx-dix-weekly-report.timer` | Sunday 00:30 UTC | Weekly DIX Telegram |
| Cron | 18:30 UTC Mon–Fri | `run_1330_strategies.sh` (paper trading) |

### ARM Regime V2 (deployed 2026-02-08)
| Regime | Weather | Flag | Conditions |
|--------|---------|------|------------|
| R0 | ☀️ CLEAR | risk_on | trend=3, iwm_rs≥0.45, vix=0 |
| R1 | 🌤️ SUNNY | risk_on | trend≥2, iwm_rs≥0.40, vix=0 |
| R1.5 | 🌥️ FAIR | risk_on | trend≥2, vix=0 |
| R5 | 🌫️ HAZE | caution | trend=1, vix=0 |
| R2 | ☁️ OVERCAST | caution | trend=0, vix=0 |
| R4 | 💨 GUSTY | caution | trend≥1, vix=1 |
| R3 | ⛈️ STORM | risk_off | trend=0, vix=1 |

**Strategy gates:** R3 blocks Bull Put. R3+R5 block Bull Put. R4: RF filter only.

### RF System
- **9 features (upgraded 2026-02-14):** regime_num, risk_off, caution, risk_on, regime_change, days_in_regime, spy_trend_score, vix_risk_flag, rs_iwm_spy
- Backfill script: `/root/projects/quantx_arm/scripts/backfill_arm_signals.py`
- Model: `/root/odte_strategy/data/rf_model.joblib` (retrained 2026-02-14, 85 labeled rows)
- Top features: rs_iwm_spy (55%), days_in_regime (30%)

---

## Critical Reminders
- **⚠️ Jan–May 2020 DIX data MISSING** — 20200101→20200416 was overwritten. Must refetch after 2021 chunk completes. Use NEW part file, Client ID 83+. Verify ≥80% close coverage before merging.
- **RF gate:** currently `RF_THR=0.10` in `.env.paper` (low gate to collect paper trade data). `RF_TRADE_THRESH=0.65` is set as the code constant — will activate when transitioning to live trading
- **After 2021 merge complete:** verify ≥80% close coverage per part → start 2022 fetch (Client ID 83) → then refetch Jan–May 2020
- **6Y fetch resume:** use `check_last_date_quality.py` to find restart point, write to NEW part file (never overwrite existing)
- **ARM future:** VIX speed signal (day-over-day change) — target before Feb 2027
- **DIX ratio per regime backtest** — target before Aug 2026
- **0DTE Distance-from-Open Backtest by Regime** — see PROJECT_ARCHIVE.md → "Priority 4: 0DTE Distance Backtest". Context: static distance rules insufficient; manual trades recently hit at 1.35% away when market moved 1.92%. Goal: regime-aware % distance grid (0.1%–2.2%) for Put/Call sides, conditioned on ARM regime, optimizing CAGR vs breach rate. Deliverable: per-regime distance rule schedule for live 0DTE placement.
- **⚠️ Strategy first confirmed trade still pending** — Bear Call skipped Feb 13 (SPX snapshot NaN). Next cron fire: 18:30 UTC Feb 18 (next trading day). Confirm TRADE_ENTER in log → update `PROJECT_ARCHIVE.md` with the IBKR leg-based pricing pattern rule for all future option spread strategies. Also update `PROJECT_OVERVIEW.md` Known Issues to mark confirmed.

---

## What to Update in PROJECT_ARCHIVE.md
Update the archive whenever any of these change — keep it current, not just historical:

| Change Type | What to Update in Archive |
|-------------|--------------------------|
| New component added (script, timer, strategy) | Add to relevant component doc section |
| Architecture change (new path, new file, renamed) | Update component docs + diagnostic commands |
| Roadmap item completed or added | Update the Roadmap table (status + date) |
| Data fetch completed (chunk, backtest) | Update 6Y Fetch Status table |
| Bug fixed with systemic lesson | Add to Session Log History with root cause |
| New scheduled timer or cron job | Add to timer list in component docs |
| Sector classification batch added | Update classification totals |

**Roadmap must stay current** — mark items ✅ DONE (with date) as they complete, add new items as they arise. The archive roadmap IS the living project roadmap.

---

## Detailed Reference
For historical sessions, roadmap, data quality tables, fetch procedures, diagnostic commands:
→ `/root/projects/PROJECT_ARCHIVE.md`

**Last Updated:** 2026-02-14
