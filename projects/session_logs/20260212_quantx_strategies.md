# Session Log — 20260212 | quantx_strategies

## Session Start
**Date:** 2026-02-12
**Context at start:** Paper trading active (DUP148773). Investigating why no trade was placed yesterday (2026-02-11) at 1:30 PM ET cron run.

---

## Tasks Completed

### [DONE] Diagnosed: No trade placed 2026-02-11 — root cause found
**Problem:** Both strategies (001 Bear Call, 002 Bull Put) have never placed a trade since deployment.
- Cron fired correctly at 18:30 UTC (1:30 PM ET) on 2026-02-11
- Bear Call ran for **1h40m** (13:30→15:10 ET), exiting with SKIP_WINDOW_EXPIRED
- Bull Put ran at 20:11 UTC (3:11 PM ET) — already outside window → SKIP_TIME
- Bear Call trade_log: **90 consecutive WAIT_NO_QUOTE events** (mid=null every retry)
- Confirmed: zero TRADE_ENTER or WAIT_CREDIT events in the entire log history

**Root cause:** `get_mid_credit(ib, spread)` used `reqMktData` with `snapshot=False` on a Bag (combo) contract. IBKR TWS does NOT reliably populate `bid`/`ask` for user-defined SPX spread Bag contracts. The Bag market data feed returns NaN/None for the combo even though individual option legs are quoted normally. This is an IBKR API limitation, not a subscription issue (OPRA subscription confirmed).

### [DONE] Fix: Both strategies — leg-based mid pricing
**Files changed:**
- `/root/projects/QuantX_Dashboard_Monitor-main/strategies_runner/001_alpha_spx_1330_0dte_bear_call.py`
- `/root/projects/QuantX_Dashboard_Monitor-main/strategies_runner/002_alpha_spx_1330_0dte_bull_put.py`

**Changes (identical pattern in both):**
1. `build_*_spread()` now returns individual leg contracts as additional return values:
   - Bear Call: `return spread, short_k, long_k, ref, sell_call, buy_call`
   - Bull Put:  `return spread, short_k, long_k, ref, sell_put, buy_put`
2. Old `get_mid_credit(ib, spread)` → removed
3. New `get_mid_credit_from_legs(ib, sell_leg, buy_leg)`:
   - Uses `snapshot=True` on each leg individually (reliable with OPRA subscription)
   - Waits 4s for both snapshots
   - Computes: `sell_mid = (bid+ask)/2`, `buy_mid = (bid+ask)/2`, `credit = sell_mid - buy_mid`
   - Returns None if any leg has invalid bid/ask, or if credit ≤ 0
4. Retry loop calls: `get_mid_credit_from_legs(ib, sell_call, buy_call)` / `(ib, sell_put, buy_put)`
5. Bag still used for order placement (unchanged)

**Syntax check:** Both scripts pass `python -m py_compile` ✅

**Pending confirmation:** Awaiting 1:30 PM ET cron run today to confirm TRADE_ENTER or WAIT_CREDIT (vs. WAIT_NO_QUOTE). If confirmed working → update PROJECT_ARCHIVE.md with this pattern note.

---

### [DONE] Diagnosed: 2021 DIX fetch Part 2 died again
- PID 2675397 (Client ID 83) — started 2026-02-11, died overnight
- Last date in file: **20210816** — 79.1% close coverage (below 80% threshold)
- File: `chunk_2021_part2_20210312_20211231.csv` (5.2MB, ~70k rows, covers 20210312→20210816)
- Part 2 covers 20210312→20210815 cleanly; 20210816 is partial (79.1%)
- Cause: likely IBKR gateway disconnection (same pattern as previous crash)

**Next action:** Restart from **20210816** (re-fetch) → write to NEW part file `chunk_2021_part3_20210816_20211231.csv`
- Client ID 83 is free (PID dead)
- Awaiting IBKR gateway reconnect (user doing 2FA login)
- Restart command (run once gateway is confirmed up):

```bash
nohup /root/odte_strategy/venv/bin/python \
  /root/projects/quantx_dix/scripts/core/compute_diy_dix_6y_optimized.py \
  --start 20210816 --end 20211231 \
  --out /root/projects/quantx_dix/data/dix/history/chunk_2021_part3_20210816_20211231.csv \
  --port 4002 --clientId 83 \
  > /root/projects/quantx_dix/logs/fetch_2021_part3.log 2>&1 &
```

---

## Next Steps
- [ ] **13:30 ET today**: Watch Telegram for TRADE_ENTER or WAIT_CREDIT on Bear Call
  - If TRADE_ENTER → strategy working ✅ → update PROJECT_ARCHIVE.md with leg-pricing note
  - If WAIT_NO_QUOTE again → individual leg snapshots also failing → deeper investigation needed
- [ ] **Once IBKR gateway up**: restart 2021 Part 3 fetch (command above)
- [ ] **After Part 3 completes**: verify ≥80% coverage all days → merge Part1 + Part2 (drop partial 20210816) + Part3 → start 2022 fetch
- [ ] After each session: `cd /root/projects && ./git-sync.sh "YYYYMMDD quantx_strategies: brief"`
- [ ] **Feb 13 ~2am NYT**: verify early weekly DIX report Telegram received ✅
- [ ] **After Feb 13**: clean up one-off systemd files (see PROJECT_ARCHIVE.md)

---

## Active Processes to Check Next Session
| Process | PID | Command |
|---------|-----|---------|
| 2021 DIX fetch Part 4 | 2875352 | Client ID 83, 20211115→20211231, chunk_2021_part4_20211115_20211231.csv |
| Strategy cron | — | 18:30 UTC daily, run_1330_strategies.sh |
| Early weekly DIX timer | — | fires 02:00 UTC Feb 13 → `quantx-dix-early-weekly-20260213.timer` |

## Key Numbers This Session
- Part 2 file: 20210312→20210816, 79.1% coverage on last day (partial)
- Strategy fix: leg-based snapshot mid pricing replaces Bag streaming
- Today's cron: 18:30 UTC (1:30 PM ET) — first live test of the fix

---

## [DONE] Early Weekly DIX Report — Emergency one-off (20260212)
**Context:** Emergency. User needs partial-week report (Feb 9–12) Telegram'd at 2am NYT Feb 13, before the regular full Sunday report.

**Changes made:**
1. **`weekly_dix_report.py`** — added `--start`/`--end` YYYYMMDD args to `main()`
   - Overrides `last_completed_mf_window()` auto-calculation when provided
   - Telegram header shows `"QuantX DIX Early Weekly Report"` when custom dates used
   - Default (no args) behaviour unchanged — Sunday timer unaffected
   - File: `/root/projects/quantx_dix/scripts/core/weekly_dix_report.py`

2. **One-off systemd service** — `/etc/systemd/system/quantx-dix-early-weekly-20260213.service`
   - Runs: `weekly_dix_report.py --start 20260209 --end 20260212`

3. **One-off systemd timer** — `/etc/systemd/system/quantx-dix-early-weekly-20260213.timer`
   - `OnCalendar=2026-02-13 02:00:00 UTC` = 2am NYT in this system's convention
   - Status: active (waiting), trigger confirmed `Fri 2026-02-13 02:00:00 UTC`

4. **PROJECT_ARCHIVE.md** — updated DIX Pipeline table + added "Early/Partial Weekly Report" reuse section

**Tonight's timeline:**
| UTC | Event |
|---|---|
| 01:00 Feb 13 | Regular daily timer → fetches Feb 12 FINRA data |
| 02:00 Feb 13 | One-off timer → early weekly report (Feb 9–12) → Telegram |
| 00:30 Feb 15 (Sun) | Regular weekly timer → full week Feb 9–13 |

**Cleanup after Feb 13:**
```bash
systemctl disable quantx-dix-early-weekly-20260213.timer
rm /etc/systemd/system/quantx-dix-early-weekly-20260213.{service,timer}
systemctl daemon-reload
```
