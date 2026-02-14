# QuantX Project Archive
**Living roadmap + detailed reference. Read when you need deep context on a specific component.**
*For current status, rules, and session start instructions, see PROJECT_OVERVIEW.md*
*Last roadmap update: 2026-02-14 (ARM history backfill 2020–2024; RF retrained 1,339 rows)*

---

# ROADMAP
**Keep this current — mark ✅ DONE (with date) as items complete. Add new items as they arise.**

## Priority 1: ARM Regime Validation (Target: Before Aug 2026)
| Task | Status |
|------|--------|
| ARM Backtest (1,533 days) | ✅ DONE 2026-02-08 |
| Fix Regime Definitions V2 | ✅ DONE 2026-02-08 |
| Strategy bug fixes (rf_prob, SPX NaN, subscription leak) | ✅ DONE 2026-02-11 |
| Strategy fix: leg-based mid pricing + tif=DAY + position guard + fill wait | ✅ DONE 2026-02-12 |
| ARM Pressure Dashboard deployed (down/up/stability/escalation in daily Telegram) | ✅ DONE 2026-02-14 |
| ARM History Backfill 2020–2024 + RF retrain (1,339 rows, AUC=0.640) | ✅ DONE 2026-02-14 |
| SPX RF model retrain with pressure features (down_pressure, up_pressure, escalation) | 🔵 NEXT |
| Bear Call RF Threshold backtest per regime | 🔵 NEXT |
| R4 Bull Put RF Threshold backtest | 🔵 NEXT |
| Multi-strategy runner: parallelise + cross-strategy position check | 🔴 NOT STARTED — required before adding 3rd+ strategy |
| VIX Speed Signal (day-over-day change as secondary panic detector) | 🔴 NOT STARTED — target before Feb 2027 |

## Priority 2: DIX Ratio Per Regime (Target: Before Aug 2026)
- Calculate DIX ratio behavior per ARM regime
- Needs full 6Y DIX data first (2020–2025)

---

## Priority 3: Intraday Crash Risk Gate for 1:30pm ET 0DTE Entry (TODO — Next Phase)

**Context:**
- Recent pattern: market opens green, then 1:50–2:30pm ET sharp selloff hits 0DTE puts.
- Daily RF (next-day market-risk model) cannot capture same-day afternoon crash risk.
- Need a separate intraday gate evaluated at ~1:20–1:30pm ET before placing the trade.

**Architecture:**
- Keep daily RF as next-day regime filter (unchanged)
- Intraday Gate = second-layer protection, 1:30pm entry only
- Gate: `IF intraday_risk_prob > X → SKIP trade  ELSE → ALLOW trade`

**Intraday Features to test (evaluated at ~1:20pm ET):**
- SPY return from open to now (open-to-1:30pm)
- SPY intraday range so far: (high - low) / open
- VIX change from open to now
- Volume spike vs 5-day average intraday profile
- Break of morning low (structure break flag)
- Distance from VWAP (optional later)

**Label Definition:**
- From 1:30pm ET to close: `min(low_1:30pm_to_close / price_at_1:30pm) - 1`
- BAD if drop exceeds threshold (e.g. -0.7% or -1.0%, configurable `INTRA_DD_THRESH`)

**Deliverables:**
1. Backtest script using 5-min or 15-min intraday SPY data
2. Breach probability vs distance-from-open grid
3. Forward validation (same 70/30 time-split approach as daily RF)
4. Simple gating rule with threshold analysis

**Data source:** yfinance `interval="5m"` or `"15m"` for historical intraday bars

**Status:** TODO — design complete, not started

---

## Priority 4: 0DTE Distance-from-Open Backtest by Regime (TODO — Later)

**Context:**
- Recent behavior: market opens green, then around 1:50–2:30pm ET can sell off aggressively.
- Manual 0DTE trades recently hit even at 1.35% away from open; market moved ~1.92%.
- Static distance rules insufficient in volatile conditions.
- Need regime-aware % distance rules for 0DTE put/call placement.

**Goal:** Backtest optimal % distance-from-OPEN for 0DTE entries, conditioned on ARM regime, to maximize CAGR while controlling breach frequency.

**Entry Times (two strategies):**
1. Midday entry: ~1:30pm ET
2. Night entry: ~10:00pm SGT

**Distance Grid:**
- Test % distance from OPEN: +0.1%, +0.2%, ..., +2.0% (put side may extend to +2.2%)
- Call breach metric: `max(high/open - 1)` → breach if >= chosen %
- Put breach metric: `min(low/open - 1)` → breach if <= -chosen %

**Backtest Steps:**
1. For each trading day: anchor on OPEN; simulate short strike at % distance; determine if intraday excursion breaches.
2. Slice by: ARM regime (R0/R1/R1.5/R2/R3/R4/R5), days_in_regime bucket, vix_risk_flag (later).
3. Metrics per (regime, distance): breach rate, trade frequency, max adverse excursion, CAGR proxy (fixed credit per distance bucket), risk-adjusted return estimate.

**Deliverables:**
- Table: best % distance per regime for Put and Call sides separately
- Plot: breach rate vs distance by regime
- Recommended regime-based distance rule schedule for live 0DTE system

**Data needed:** SPX (or SPY) intraday OHLC by date; ARM regime history (`arm_regime_historical.csv` + live `arm_state_history.csv`)

## Priority 3: 6Y Historical Data Completion (Target: Before Mar 2026)
| Chunk | Date Range | Status | Notes |
|-------|------------|--------|-------|
| 2020 Apr–Dec | 20200417→20201231 | ✅ COMPLETE | 129,251 rows, 97.77% coverage |
| **2020 Jan–Apr** | **20200101→20200416** | **⚠️ MUST REFETCH** | **Overwritten — fetch after 2021 done. New part file, Client ID 83+** |
| 2021 Part 1 | 20210104→20210311 | ✅ FETCHED | trim to 20210311 (20210312 = 21.3% bad) |
| 2021 Part 2 | 20210312→20210813 | ✅ FETCHED | trim to 20210813 (20210816 = 79.1% low) |
| 2021 Part 3 | 20210816→20211115 | ✅ FETCHED | trim to 20211115 (20211116 = 44.2% bad) |
| 2021 Part 4 | 20211115→20211231 | ✅ COMPLETE | 99.0% coverage, 20211231 clean — all 4 parts cover full year ⚠️ MERGE PENDING |
| 2022 | 20220103→20221230 | 🔵 NEXT | Start after 2021 merge, Client ID 83 |
| 2023–2025 | TBD | ⏳ PENDING | Lower priority |

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
| `weekly_dix_report.py` | Weekly Telegram summary (accepts `--start`/`--end` YYYYMMDD for partial/early reports) | N/A |
| `daily_precious_metals_report.py` | Precious metals report | N/A |
| `update_history_master.py` | Merge daily into master | N/A |

### Early/Partial Weekly Report (one-off)
Use when you need an early report mid-week (e.g. emergency, public holiday):
**Last used: 2026-02-13 02:00 UTC → Feb 9–12 report ✅ delivered + systemd files cleaned up**
```bash
# Systemd files (create fresh each time — template below):
# quantx-dix-early-weekly-YYYYMMDD.service: edit --start/--end dates
# quantx-dix-early-weekly-YYYYMMDD.timer:   edit OnCalendar date/time (always UTC)

# To set up for a new date:
# 1. Copy/edit the service + timer files with the new date
# 2. systemctl daemon-reload
# 3. systemctl enable --now quantx-dix-early-weekly-<YYYYMMDD>.timer
# 4. Verify: systemctl list-timers quantx-dix-early-weekly-<YYYYMMDD>.timer

# Cleanup after firing:
# systemctl disable quantx-dix-early-weekly-<YYYYMMDD>.timer
# rm /etc/systemd/system/quantx-dix-early-weekly-<YYYYMMDD>.{service,timer}
# systemctl daemon-reload
```
- Timer convention: fires at `HH:MM UTC` (system clock is UTC; "1am NYT" = 01:00 UTC, "2am NYT" = 02:00 UTC in this setup)
- `weekly_dix_report.py --start YYYYMMDD --end YYYYMMDD` — Telegram header shows "Early Weekly Report"; default (no args) = normal Sunday behaviour unchanged

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

RF features (current, 6): `regime_num`, `risk_off`, `caution`, `risk_on`, `regime_change`, `days_in_regime`
- `regime_num` = float of regime label string (R1.5→1.5), NOT the pressure `_REGIME_RANK` ordering
- Will auto-upgrade to 9 features once `spy_trend_score`/`vix_risk_flag`/`rs_iwm_spy` hit >50% fill

### ARM Pressure Dashboard (deployed 2026-02-14)
**File:** `quantx_arm/arm_regime_engine.py` — replaces Telegram message, runs within existing daily job

**State file:** `quantx_arm/state/pressure_state.json` — carries today's `vix_close` + scores as tomorrow's "yesterday". Cold start: `vix_pct=0`, all pressure=0 (safe).

**Locked parameters (grid search, 108 combos, properly warmup-buffered):**
```python
VIX_SPIKE_DOWN_PCT = 0.08   VIX_SPIKE_DOWN_ABS = 2.0   # strict — spikes are sharp
VIX_SPIKE_UP_PCT   = 0.08   VIX_SPIKE_UP_ABS   = 1.0   # relaxed — drops are gradual
VIX_GAP_NEAR_MA    = 0.5    STABILITY_GATE     = 2
```

**Formulas:**
```
down_pressure   = vix_spike_down + trend_dropped  + regime_worsened   (0–3)
up_pressure     = vix_spike_up   + trend_improved + regime_improved   (0–3)
stability_score = regime_flipped + vix_near_ma    + trend_changed     (0–3)
escalation      = (down_pressure == 3) AND (stability_score >= 2)
```

**Validation:** 2020 crash → Feb 24 caught day-of; 2024 H1 bull → 0 false alarms; recent 6m → 9 escalation days, all legitimate STORM/GUSTY periods.

## Paper Trading Setup
- Account: DUP148773 (username: jaszzzsgapi-paper)
- Cron: `30 18 * * 1-5 /root/projects/QuantX_Dashboard_Monitor-main/run_1330_strategies.sh`
- Bear Call: OTM=30pts, width=5pts, min_credit=$1.00, RF_THR=0.10 (trial)
- Bull Put: OTM=20pts, width=5pts, min_credit=$1.00, ARM gate (skip R3)
- Bear flag: `/root/odte_strategy/state/bear_call_active_today.json` — if Bear Call trades, Bull Put skips
- Runner: **sequential** (001 → 002). Must parallelise before adding 3rd+ strategy or window timing degrades
- Fill monitor: `strategies_runner/fill_monitor.py` — runs hourly 10am–4pm ET (cron: `0 15-21 * * 1-5`), generic (scans all `*/trade_log.csv`), logs `TRADE_FILL` + Telegram `🎯 FILLED` on confirmation. Log: `strategies_runner/logs/fill_monitor.log`

### Strategy Design Rules (MANDATORY for all future strategies)
1. **`tif="DAY"`** on all `LimitOrder` calls — order persists after disconnect
2. **Fill-wait loop** after `placeOrder` — poll up to 90s for `Filled`/`Cancelled` before returning
3. **Position guard** before entry — call `ib.positions()` and skip if SPXW legs for today's expiry already exist (prevents duplicates on reruns or cron overlap)
4. **Each strategy gets unique Client ID** via `get_client_id()` registry
5. **IBKR Bag/combo `reqMktData` unreliable for SPX spreads** — always use leg-based snapshot pricing (`get_mid_credit_from_legs`)
6. **Closing the terminal does NOT disconnect** — strategy disconnects in its own `finally` block after logging `TRADE_ENTER`
7. **SPX snapshot retry** — `get_spx_price_and_contract()` retries `reqMktData(snapshot=True)` up to 3 times (3s each) before raising. Transient gateway NaN can occur even in normal market hours.

---

# SESSION LOG HISTORY
*(Sessions before 2026-02-11 — moved from PROJECT_OVERVIEW.md)*

## 2026-02-14 — ARM Pressure Dashboard + 2021 DIX Part 4 complete
- ARM Pressure Dashboard deployed in `arm_regime_engine.py` (replaces Telegram message)
- Locked params: down abs=2.0, up abs=1.0, pct=0.08, gap=0.5, stability gate=2
- `pressure_state.json` added to `quantx_arm/state/` for yesterday/today comparison
- SPX snapshot retry (3 attempts) deployed in 001+002 strategies
- 2021 DIX Part 4 complete: PID 2875352 finished, 20211115→20211231, 99.0% coverage
- Full 2021 year covered (Parts 1–4) — merge pending before starting 2022 fetch

## 2026-02-12–13 — Strategy fill fix + fill monitor + early weekly DIX
- Strategy fix: `tif=DAY`, 90s fill-wait loop, position guard in 001+002
- Fill monitor: hourly 10am–4pm ET, generic multi-ticker, `fill_monitor.py`
- Early weekly DIX report (Feb 9–12) delivered via systemd one-shot timer, files cleaned up

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
*Last archived: 2026-02-14*
