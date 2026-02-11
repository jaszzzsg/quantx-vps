# Paper Trading Trial Setup - Complete Summary

**Trial Period**: February 2-6, 2026 (5 trading days)
**Objective**: Verify trade placement works correctly for both Bear Call and Bull Put strategies
**Account**: Paper Trading (IB Gateway port 4002, Account DU9186063)
**Setup Date**: January 31, 2026

---

## What Was Changed

### 1. RF Threshold Lowered (Bear Call Strategy Only)

**File**: [strategies_runner/001_alpha_spx_1330_0dte_bear_call.py:48-51](strategies_runner/001_alpha_spx_1330_0dte_bear_call.py#L48-L51)

```python
# BEFORE (Original - Production Setting)
RF_THRESHOLD = 0.60  # 60% probability required

# AFTER (Trial - Temporary for Feb 2-6)
RF_THRESHOLD = 0.10  # 10% probability (lowered for testing)
```

**Impact**: Bear Call strategy will now trade when RF probability is as low as 10%, instead of requiring 60%. This allows testing during typical market conditions.

**⚠️ CRITICAL**: Must be restored to **0.60** after trial ends on **February 7, 2026**

---

### 2. Bull Put Strategy (No Changes Needed)

**File**: [strategies_runner/002_alpha_spx_1330_0dte_bull_put.py](strategies_runner/002_alpha_spx_1330_0dte_bull_put.py)

**No RF threshold** - Bull Put strategy only uses:
- ARM regime gate (skips if R3)
- Bear Call mutual exclusivity (skips if Bear Call traded today)
- Time window (1:30-3:10 PM ET)
- Credit requirement (>= $1.00)

**No changes required for this strategy.**

---

## Files Created for Trial Management

### 1. Configuration Backup
**File**: [PAPER_TRIAL_CONFIG_BACKUP.json](PAPER_TRIAL_CONFIG_BACKUP.json)

Contains:
- Original RF_THRESHOLD value (0.60) for restoration
- Current market state snapshot (ARM regime, RF probability)
- Strategy details and gate conditions
- Trial checklist and monitoring guidelines
- Restore instructions

**Purpose**: Reference document with all original settings and trial metadata

---

### 2. Feb 7 Reminder Script
**File**: [feb7_trial_reminder.py](feb7_trial_reminder.py)

**Scheduled**: February 7, 2026 at 9:00 AM ET (via crontab)

**Actions**:
- ✅ Automatically sends Telegram reminder on Feb 7
- 📊 Includes trial summary (# of trades placed)
- ⚠️ Reminds to restore RF_THRESHOLD to 0.60
- 📝 Provides step-by-step restoration instructions

**Crontab Entry**:
```bash
0 9 7 2 * /root/odte_strategy/venv/bin/python /root/projects/QuantX_Dashboard_Monitor-main/feb7_trial_reminder.py
```

**Manual Run** (if needed):
```bash
/root/odte_strategy/venv/bin/python feb7_trial_reminder.py
```

---

### 3. Daily Progress Checker
**File**: [check_trial_progress.py](check_trial_progress.py)

**Run Daily During Trial**:
```bash
cd /root/projects/QuantX_Dashboard_Monitor-main
/root/odte_strategy/venv/bin/python check_trial_progress.py
```

**Shows**:
- Current trial day (e.g., "Day 3 of 5")
- Current market conditions (ARM regime, RF probability)
- Bear Call trades placed
- Bull Put trades placed
- Skip reasons and error counts
- Recent trade details (strikes, credits, status)
- Recommendations and next steps

**Recommended**: Run this every afternoon after 3:10 PM ET to review the day's activity

---

### 4. Component Diagnostic Script
**File**: [test_strategy_components.py](test_strategy_components.py)

**Run Once Before Trial Starts** (Optional):
```bash
/root/odte_strategy/venv/bin/python test_strategy_components.py
```

Tests:
- Time zone configuration
- ARM regime loading
- RF predictions loading
- Logging system
- IB Gateway connection
- SPX market data access
- Option chain availability
- Telegram notifications

**Purpose**: Pre-flight check to ensure all components work before trial begins

---

## Original Settings (For Reference)

| Parameter | Original Value | Trial Value | Strategy |
|-----------|---------------|-------------|----------|
| RF_THRESHOLD | **0.60** (60%) | 0.10 (10%) | Bear Call (001) |
| ARM Regime Gate | N/A (no change) | N/A | Bull Put (002) |
| OTM_POINTS (Bear) | 30 | 30 (unchanged) | Bear Call (001) |
| OTM_POINTS (Bull) | 20 | 20 (unchanged) | Bull Put (002) |
| WIDTH | 5 | 5 (unchanged) | Both |
| MIN_CREDIT | $1.00 | $1.00 (unchanged) | Both |
| Entry Window | 1:30-3:10 PM ET | 1:30-3:10 PM ET (unchanged) | Both |
| Retry Interval | 60 seconds | 60 seconds (unchanged) | Both |

**Current Market State** (as of Jan 30, 2026):
- ARM Regime: **R4**
- RF Probability: **43.79%** (below original 60% threshold, above trial 10% threshold)
- VIX: 17.29 (VIX MA: 15.52)

---

## What to Expect During Trial

### Daily Trading Pattern (Mon-Fri)

**1:30 PM ET**: Scripts run (triggered by your external scheduler)

**Strategy Priority**:
1. **Bear Call (001)** tries first
   - If RF ≥ 10%: Attempts to place trade
   - If successful: Sets "bear call active today" flag
   - If failed: Retries every 60 seconds until 3:10 PM or successful

2. **Bull Put (002)** tries second (if Bear Call didn't trade)
   - Checks: Bear Call active? → Skip if yes
   - Checks: ARM regime R3? → Skip if yes
   - If clear: Attempts to place trade
   - If failed: Retries every 60 seconds until 3:10 PM or successful

**3:10 PM ET**: Entry window closes
- If no trade placed by 3:10 PM: SKIP_WINDOW_EXPIRED notification sent

---

### Telegram Notifications You'll Receive

#### ✅ ENTER (Trade Placed Successfully)
```
✅ ENTER
SPXW BEAR_CALL
Exp: 20260203
Strikes: 6085/6090
Credit: $1.25
status=Submitted spx=6055.00 ref=6055 rf=0.438 regime=R4
Time: 2026-02-03 18:35:00 UTC
```

**What to check**:
- ✓ Expiry is today's date (0DTE)
- ✓ Strikes make sense:
  - Bear Call: Short = SPX + 30, Long = Short + 5
  - Bull Put: Short = SPX - 20, Long = Short - 5
- ✓ Credit ≥ $1.00
- ✓ Trade appears in IB paper account

#### ⏭️ SKIP (Trade Skipped)
```
⏭️ SKIP
SPXW BEAR_CALL
Reason: RF<0.1 or missing
rf_prob=0.08 date=2026-02-04 regime=R4
Time: 2026-02-04 18:30:00 UTC
```

**Common Skip Reasons**:
- `SKIP_TIME`: Outside 1:30-3:10 PM ET window
- `SKIP_RF`: RF probability < 0.10 (Bear Call only)
- `SKIP_ARM_R3`: ARM regime is R3 (Bull Put only)
- `SKIP_BEAR_ACTIVE`: Bear Call already traded today (Bull Put only)
- `SKIP_IB_DOWN`: Can't connect to IB Gateway
- `SKIP_WINDOW_EXPIRED`: Retried until 3:10 PM, never got credit ≥ $1.00

---

## Daily Monitoring Checklist

### Every Day During Trial (Feb 2-6):

- [ ] **Check Telegram** for ENTER/SKIP notifications
- [ ] **Run progress checker**:
  ```bash
  /root/odte_strategy/venv/bin/python check_trial_progress.py
  ```
- [ ] **Verify IB Gateway is running** on port 4002
- [ ] **Check IB paper account** to confirm trades appear
- [ ] **Review trade details**:
  - Strike selection correct?
  - Credit amount ≥ $1.00?
  - Expiry is today (0DTE)?
- [ ] **Note any errors** or unexpected behavior

---

## End of Trial Checklist (Feb 7)

### You'll Receive Telegram Reminder at 9:00 AM ET

**Actions Required**:

1. **Review Trial Results**
   ```bash
   /root/odte_strategy/venv/bin/python check_trial_progress.py
   ```

2. **Restore RF_THRESHOLD** ⚠️ **CRITICAL**
   - Edit: [strategies_runner/001_alpha_spx_1330_0dte_bear_call.py:48-51](strategies_runner/001_alpha_spx_1330_0dte_bear_call.py#L48-L51)
   - Change FROM:
     ```python
     # PAPER TRIAL: 2026-02-02 to 2026-02-06
     # ORIGINAL: RF_THRESHOLD = 0.60 (60%)
     # RESTORE TO 0.60 ON 2026-02-07!
     RF_THRESHOLD = 0.10  # Lowered for paper trading trial
     ```
   - Change TO:
     ```python
     # ----- gates / parameters -----
     RF_THRESHOLD = 0.60
     ```

3. **Verify Restoration**
   ```bash
   grep "RF_THRESHOLD" strategies_runner/001_alpha_spx_1330_0dte_bear_call.py
   ```
   Should show: `RF_THRESHOLD = 0.60`

4. **Update Restore Log**
   - Edit: [PAPER_TRIAL_CONFIG_BACKUP.json](PAPER_TRIAL_CONFIG_BACKUP.json)
   - Find `restore_log` section
   - Update:
     ```json
     "restore_log": {
       "restored": true,
       "restored_date": "2026-02-07",
       "restored_by": "Your Name",
       "notes": "Trial completed successfully. RF_THRESHOLD restored to 0.60"
     }
     ```

5. **Review Trial Results**
   - How many trades were placed?
   - Were strikes selected correctly?
   - Did trades fill with credit ≥ $1.00?
   - Any errors or issues encountered?
   - Did notification system work reliably?

---

## Trade Validation Guide

### What to Look For in IB Paper Account

**Bear Call Spread**:
- Symbol: SPX (or SPXW)
- Type: CALL spread
- Expiry: Today's date (0DTE)
- Short Strike: SPX price + 30 points (rounded to nearest 5)
- Long Strike: Short strike + 5 points
- Quantity: 1 contract
- Credit: ≥ $1.00 per spread
- Example: SPX @ 6055 → Sell 6085 Call, Buy 6090 Call for $1.25 credit

**Bull Put Spread**:
- Symbol: SPX (or SPXW)
- Type: PUT spread
- Expiry: Today's date (0DTE)
- Short Strike: SPX price - 20 points (rounded to nearest 5)
- Long Strike: Short strike - 5 points
- Quantity: 1 contract
- Credit: ≥ $1.00 per spread
- Example: SPX @ 6055 → Sell 6035 Put, Buy 6030 Put for $1.15 credit

**Mutual Exclusivity**:
- Only **ONE** strategy should trade per day
- If Bear Call trades → Bull Put should SKIP_BEAR_ACTIVE
- If Bear Call skips (all day) → Bull Put can trade

---

## Troubleshooting

### Issue: No trades are being placed

**Check**:
1. **IB Gateway running?**
   ```bash
   ps aux | grep -i gateway
   ```
   Should show IB Gateway process

2. **Scripts running during 1:30-3:10 PM ET?**
   - Check your external scheduler (cron, etc.)
   - Scripts must run within the entry window

3. **Check Telegram for skip reasons**
   - SKIP_IB_DOWN → IB Gateway connection failed
   - SKIP_WINDOW_EXPIRED → Credit never reached $1.00

4. **Check current RF probability**
   ```bash
   tail -2 /root/odte_strategy/data/rf_daily_predictions.csv
   ```
   Even with trial threshold (0.10), RF might be lower

5. **Run diagnostic**
   ```bash
   /root/odte_strategy/venv/bin/python test_strategy_components.py
   ```

---

### Issue: Trades placing with wrong strikes

**Expected Strike Calculation**:

**Bear Call**:
- Reference: `floor(SPX / 5) * 5` (round down to nearest 5)
- Short Call: Reference + 30
- Long Call: Short + 5
- Example: SPX=6057.23 → Ref=6055 → Short=6085, Long=6090

**Bull Put**:
- Reference: `floor(SPX / 5) * 5`
- Short Put: Reference - 20
- Long Put: Short - 5
- Example: SPX=6057.23 → Ref=6055 → Short=6035, Long=6030

If strikes don't match this formula, report in trial results.

---

### Issue: Telegram notifications not sending

**Check environment variables**:
```bash
echo "TG_BOT_TOKEN: ${TG_BOT_TOKEN:0:10}..."
echo "TG_CHAT_ID: $TG_CHAT_ID"
```

**Test notification**:
```bash
/root/odte_strategy/venv/bin/python -c "
import sys
sys.path.append('/root/projects/QuantX_Dashboard_Monitor-main')
from utils.tg_notify import tg_send
tg_send('Test from trial setup')
"
```

---

## Quick Reference Commands

```bash
# Check trial progress (run daily)
/root/odte_strategy/venv/bin/python check_trial_progress.py

# Test all components (run before trial starts)
/root/odte_strategy/venv/bin/python test_strategy_components.py

# Manually trigger Feb 7 reminder
/root/odte_strategy/venv/bin/python feb7_trial_reminder.py

# View Bear Call logs
tail -20 strategies_runner/logs/001_alpha_spx_1330_0dte_bear_call/trade_log.csv

# View Bull Put logs
tail -20 strategies_runner/logs/002_alpha_spx_1330_0dte_bull_put/trade_log.csv

# Check current RF threshold (should be 0.10 during trial)
grep "RF_THRESHOLD" strategies_runner/001_alpha_spx_1330_0dte_bear_call.py

# Check crontab (Feb 7 reminder)
crontab -l

# Check current market conditions
cat /root/projects/quantx_arm/state/regime_state.json | python3 -m json.tool
tail -2 /root/odte_strategy/data/rf_daily_predictions.csv
```

---

## Important Notes

### ⚠️ Critical Reminders

1. **This is PAPER TRADING** (IB port 4002, account DU9186063)
   - No real money at risk
   - Safe to test and verify trade placement

2. **RF_THRESHOLD MUST be restored to 0.60 on Feb 7**
   - Current: 0.10 (trial)
   - Production: 0.60 (60% probability required)
   - Leaving at 0.10 would trade low-quality setups!

3. **Only ONE strategy trades per day**
   - Bear Call has priority
   - Bull Put only trades if Bear Call skipped

4. **Trial runs Feb 2-6 (5 trading days)**
   - Max 5 total trades (one per day)
   - Could be fewer if market conditions cause skips

### 📱 Telegram Reminder

You will receive an automatic Telegram reminder on **February 7, 2026 at 9:00 AM ET** with:
- Trial summary (total trades placed)
- Step-by-step restoration instructions
- Reminder to restore RF_THRESHOLD to 0.60

---

## Files Summary

| File | Purpose | When to Use |
|------|---------|-------------|
| [PAPER_TRIAL_CONFIG_BACKUP.json](PAPER_TRIAL_CONFIG_BACKUP.json) | Original settings backup | Reference for restoration |
| [feb7_trial_reminder.py](feb7_trial_reminder.py) | Auto-reminder script | Runs automatically Feb 7 |
| [check_trial_progress.py](check_trial_progress.py) | Daily progress checker | Run daily during trial |
| [test_strategy_components.py](test_strategy_components.py) | Component diagnostics | Run before trial starts |
| [strategy_diagnostic_report.md](strategy_diagnostic_report.md) | Detailed analysis | Reference for understanding |
| [TRIAL_SETUP_SUMMARY.md](TRIAL_SETUP_SUMMARY.md) | This file | Your main guide |

---

## Support

If you encounter issues during the trial:

1. **Run progress checker** to see current status
2. **Check Telegram** for skip/error messages
3. **Review logs** in `strategies_runner/logs/*/trade_log.csv`
4. **Test components** with diagnostic script
5. **Verify IB Gateway** is running on port 4002

---

**Setup Complete!** ✅

You're all set for the paper trading trial Feb 2-6, 2026.

**Next Steps**:
1. (Optional) Run `test_strategy_components.py` before Feb 2 to verify everything works
2. Run `check_trial_progress.py` daily during Feb 2-6 to monitor
3. Wait for Feb 7 Telegram reminder to restore settings
4. Review results and restore RF_THRESHOLD to 0.60

---

**Trial Setup Date**: January 31, 2026
**Original RF_THRESHOLD**: 0.60 (60%)
**Trial RF_THRESHOLD**: 0.10 (10%)
**Restore Date**: February 7, 2026
