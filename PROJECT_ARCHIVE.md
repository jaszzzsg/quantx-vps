# QuantX Project Archive
**Historical reference — not required reading every session. Read when you need deep context.**
*For current status and rules, see PROJECT_OVERVIEW.md*

---

# ROADMAP

## Priority 1: ARM Regime Validation (Target: Before Aug 2026)
| Task | Status |
|------|--------|
| ARM Backtest (1,533 days) | ✅ DONE 2026-02-08 |
| Fix Regime Definitions V2 | ✅ DONE 2026-02-08 |
| Bear Call RF Threshold backtest | 🔵 NEXT |
| R4 Bull Put RF Threshold backtest | 🔵 NEXT |
| VIX Speed Signal (day-over-day change) | 🔴 NOT STARTED — target before Feb 2027 |

## Priority 2: DIX Ratio Per Regime (Target: Before Aug 2026)
- Calculate DIX ratio behavior per ARM regime
- Need full 6Y DIX data first (2020–2025)

## Priority 3: 6Y Historical Data Completion (Target: Before Mar 2026)
| Chunk | Status |
|-------|--------|
| 2020 | ✅ COMPLETE — 129,251 rows, 97.77% coverage |
| 2021 | 🚀 RUNNING — PID 2610294, Client ID 82 |
| 2022 | ⏳ PENDING — start after 2021 complete, Client ID 83 |
| 2023–2025 | ⏳ PENDING |

### 6Y Fetch Commands
```bash
# Start new chunk
cd /root/projects/quantx_dix
nohup .venv/bin/python scripts/core/compute_diy_dix_6y_optimized.py \
  --start YYYYMMDD --end YYYYMMDD \
  --out data/dix/history/chunk_YYYY.csv \
  --clientId 82 > logs/chunk_YYYY_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo "PID: $!"

# If fetch dies — check quality of existing file
.venv/bin/python scripts/tools/check_last_date_quality.py data/dix/history/chunk_YYYY.csv
# Then restart to NEW part file (NEVER reuse same --out, script opens in "w" mode)
```

## Priority 4: Sector Classification (Ongoing — keep unnamed out of top 5)
- Total classified: 1,064 tickers (Feb 8, 2026)
- Daily unnamed: $10.10B (position #8) ✅
- Weekly unnamed: out of top 6 ✅
- Check: `cd /root/projects/quantx_dix && .venv/bin/python scripts/tools/check_unnamed_sector.py`

## Priority 5: Sector Rotation Early Detection (Target: Before Oct 2026)
- Not started — needs 6Y data complete first

---

# DETAILED COMPONENT DOCS

## DIX Pipeline
| Script | Purpose | Client ID |
|--------|---------|-----------|
| `compute_diy_dix_one_day_ibkr.py` | Daily DIX fetch | 22 |
| `compute_diy_dix_6y_optimized.py` | Historical 6Y fetch | 80/82 (manual) |
| `weekly_dix_report.py` | Weekly Telegram summary | N/A |
| `daily_precious_metals_report.py` | Precious metals report | N/A |
| `update_history_master.py` | Merge daily into master | N/A |

Data paths:
- Daily details: `/root/projects/quantx_dix/data/dix/details/`
- History master: `/root/projects/quantx_dix/data/dix/history/`
- FINRA cache: `/root/projects/quantx_dix/data/finra_cache/short_volume/`
- Logs: `/root/projects/quantx_dix/logs/`

## ARM Regime — Full Reference
See: `/root/projects/quantx_arm/ARM_REGIME_REFERENCE.md`

RF feature pipeline:
1. ARM regime updates daily (14:45 UTC) via `arm_regime_engine.py`
2. `arm_history_append.py` appends to ARM history — reads `spy_trend_score/vix_risk_flag/iwm_spy_rs` from `s["scores"]` dict (bug fixed Feb 8, 2026)
3. `rf_score_daily.py` calculates RF probability
4. Model: `/root/odte_strategy/data/rf_model.joblib`
5. Metadata: `/root/odte_strategy/data/rf_model_meta.json`

RF features: regime_num, risk_off, caution, risk_on, regime_change, days_in_regime (6 now; will auto-upgrade to 9 with spy_trend_score, vix_risk_flag, rs_iwm_spy once >50% fill)

## Paper Trading Setup
- Account: DUP148773 (username: jaszzzsgapi-paper)
- Cron: `30 18 * * 1-5 /root/projects/QuantX_Dashboard_Monitor-main/run_1330_strategies.sh`
- Bear Call: OTM=30pts, width=5pts, min_credit=$1.00, RF_THR=0.10 (trial)
- Bull Put: OTM=20pts, width=5pts, min_credit=$1.00, ARM gate (skip R3)
- Bear flag: `/root/odte_strategy/state/bear_call_active_today.json` — if Bear Call trades, Bull Put skips

---

# SESSION LOG HISTORY
*(Sessions before 2026-02-11 — moved from PROJECT_OVERVIEW.md)*

## 2026-02-10 — Fix RF pipeline, duplicate runner, account correction
- Fixed `.env.paper` inline comment on RF_THR → systemd was reading `0.10# Lowered...` as float → crash
- Fixed `run_1330_strategies.sh`: sources `.env.paper`, exports TG vars, removed `set -e`
- Fixed IB_ACCOUNT DU9186063 → DUP148773 in both strategies
- Backfilled RF row for 20260210 manually
- Disabled + removed `odte-strategy.timer` (duplicate runner)

## 2026-02-08 Part 2 — DIX weekly report + sector classification batches 5+6
- Fixed `weekly_dix_report.py`: Top 5 → Top 6 sectors
- Batch 5: 26 ETFs + 75 stocks (998 total)
- Batch 6: 23 ETFs + 43 stocks (1,064 total)
- Unnamed daily: $25.26B → $10.10B (position #4 → #8)
- Resent Feb 2–6 weekly report

## 2026-02-08 — 2020 data finalization, paper trading setup, 2021 fetch start
- chunk_2020.csv: 129,251 rows, 20200417–20201231, 97.77% close coverage — FINAL
- Set up paper trading cron at 18:30 UTC weekdays
- ARM Regime V2 deployed (R5=early recovery, R3=pure breakdown, flags corrected)
- Fixed VIX MA bug (now uses true 20-day rolling MA)
- Started 2021 fetch: PID 2426157, Client ID 82
- arm_history_append.py bug fixed: reading from `s["scores"]` dict

## 2026-02-03 — IBKR connection fix, 6Y fetch Part 1
- Removed `util.logToConsole(logging.WARNING)` from 6Y script (was causing gateway hang)
- Simplified `connect_ib_with_retry()`, reduced max_tries to 5
- Restarted gateway (killed PIDs 2177845/2177846/2178151), restarted port 4002
- Started Part 1 (20200417–20200527)

## 2026-02-02 — Sector classification batches 1–4
- Classified 100 tickers (Batches 1–2), unnamed moved from top 5 → position 7 daily
- Added 55 ETFs to etf_classification_master.csv (160→215)
- Fixed weekly_dix_report.py field mapping: category→industry
- Resent corrected Telegram reports for Jan 19–23 and Jan 26–30

## 2026-02-01 — Weekly DIX report fix, 6Y fetch restart
- Fixed TypeError in weekly_dix_report.py (NaN in precious_override)
- Diagnosed chunk 2020 Part 2 stopped at 40 days
- Started chunk 2020 Part 3 from July 23 → Dec 31

## 2026-01-31 — Paper trading trial setup, chunk 2020 data validation
- Lowered RF_THRESHOLD 0.60 → 0.10 for Feb 2–6 trial
- Discovered chunk 2020 had only 35/185 days due to connection loss
- Added reconnection logic to compute_diy_dix_6y_optimized.py

## 2026-01-31 Part 1 — Client ID management
- Built centralized client ID manager at `/root/shared/ibkr/`
- Created CLIENT_ID_REGISTRY.md
- Added readonly mode to IBKR connections

---

# COMMON DIAGNOSTIC COMMANDS

```bash
# Check running processes
ps aux | grep -E "compute_diy|arm_regime|chunk" | grep -v grep

# Check specific PID
ps -p <PID> -o pid,cmd

# Check chunk fetch progress
tail -20 /root/projects/quantx_dix/logs/chunk_*.log

# Check timers
systemctl list-timers --all | grep -E "quantx|arm|rf"

# Check service logs
journalctl -u arm-rf-update.service -n 50
journalctl -u quantx-dix-daily.service -n 50

# Get new IBKR client ID
python << 'END'
import sys; sys.path.insert(0, '/root/shared/ibkr')
from client_id_manager import get_client_id
print(get_client_id('127.0.0.1', 4002, 'purpose', 'project'))
END
```

---
*Last archived: 2026-02-11*
