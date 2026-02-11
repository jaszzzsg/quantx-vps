# QuantX Projects Overview
**For Claude AI Assistant — Read This First Every Session**

---

## Quick Start (Every Session)
1. Read this file
2. Read the latest session log: `ls -t /root/projects/session_logs/ | head -1` then read that file
3. Check any active PIDs from session log are still running
4. Ask user what to work on (or continue from session log's Next Steps)

## Session Log System
- **Location:** `/root/projects/session_logs/YYYYMMDD_quantx.md`
- **One file per day** — append if multiple sessions on same day
- **At session start:** read latest log for full context on what was done and what's next
- **During session:** update the log as each task completes (so crashes/context limits don't lose progress)
- **At session end:** mark completed items, write Next Steps, note any active PIDs

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

**As of 2026-02-11:**
- Paper trading ACTIVE — cron at 18:30 UTC (1:30 PM ET) weekdays, account DUP148773
- RF_THRESHOLD = 0.10 (trial mode — restore to 0.60 after enough paper trades collected)
- 2021 DIX fetch: PID 2610294, Client ID 82 (20210104→20211231, started Feb 10 ~17:10 UTC)
- RF pipeline bugs fixed (see session log 20260211_quantx.md)

## Known Issues
- `rf_daily_predictions.csv` has junk row with date `19700101` (epoch artifact) — cosmetic only, upsert deduplicates
- 2021 DIX fetch script uses `open("w")` — if it dies, must restart from day 1, never resume mid-file

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
| 4002 | PAPER | 22 (DIX daily), 82 (6Y fetch), 991 (ARM VIX) |

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
- 6 features: regime_num, risk_off, caution, risk_on, regime_change, days_in_regime
- Will auto-upgrade to 9 features once spy_trend_score/vix_risk_flag/rs_iwm_spy fill >50%
- Model: `/root/odte_strategy/data/rf_model.joblib`

---

## Critical Reminders
- **Restore RF_THRESHOLD to 0.60** in Bear Call after paper trade validation complete
- **After 2021 fetch complete:** verify ≥80% close coverage, then start 2022 fetch (Client ID 83)
- **6Y fetch resume:** use `check_last_date_quality.py` to find restart point, write to NEW part file (never overwrite)
- **ARM future:** VIX speed signal (vix day-over-day change) — target before Feb 2027
- **DIX ratio per regime backtest** — target before Aug 2026

---

## Detailed Reference
For historical session logs, old roadmap, data quality tables, fetch recovery procedures:
→ `/root/projects/PROJECT_ARCHIVE.md`

**Last Updated:** 2026-02-11
