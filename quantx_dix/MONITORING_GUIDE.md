# IBKR Chunk 2020 Fetch - Monitoring Guide

## Quick Start

### 1. Live Progress Monitor (VS Code Terminal)
Shows a real-time progress bar with current status:

```bash
bash monitor.sh
```

**What you'll see:**
- Real-time progress bar (updates every 5 seconds)
- Current date being processed
- Speed (days per hour)
- ETA and estimated finish time
- Symbol count

Press `Ctrl+C` to stop monitoring (fetch continues in background)

---

### 2. Watchdog (Background Process)
Monitors the fetch process and sends **Telegram alerts** if it dies:

```bash
bash watchdog.sh
```

**What it does:**
- ✅ Checks every 60 seconds if the process is running
- ✅ Monitors if the log file is being updated
- ✅ Sends you a Telegram message if:
  - Process dies/crashes
  - Process is stuck (log not updating for 10+ minutes)
  - Process restarts

**Check watchdog status:**
```bash
tail -f logs/watchdog_2020.log
```

**Stop watchdog:**
```bash
kill $(cat logs/watchdog_2020.pid)
```

---

## Quick Status Check

```bash
bash quick_check.sh
```

Shows current progress without continuous monitoring.

---

## Telegram Alerts

The watchdog will send you messages like:

**If process dies:**
```
🚨 ALERT: IBKR Chunk 2020 Fetch STOPPED!

Time: 2026-01-31 14:30:00
Process: compute_diy_dix_6y_optimized.py
Client ID: 80

Last progress:
[6%] Day 12/185 20200504 | 777 syms | 5.1 d/hr | ETA: 33.9h

Please check your VPS!
```

**If process is stuck:**
```
⚠️ WARNING: IBKR Chunk 2020 Fetch may be STUCK!

Process is running but log hasn't updated in 15 minutes
Time: 2026-01-31 14:30:00

Last progress:
[6%] Day 12/185 20200504 | 777 syms | 5.1 d/hr | ETA: 33.9h

Check if IBKR Gateway is running or if there's a network issue.
```

---

## Recommended Setup

**Option 1: VS Code Terminal (Interactive)**
1. Open terminal in VS Code
2. Run `bash monitor.sh`
3. Leave it running while you work
4. You'll see live updates

**Option 2: Background Monitoring**
1. Start watchdog: `bash watchdog.sh`
2. Close VS Code and go about your day
3. You'll get Telegram alerts if anything goes wrong
4. Check status anytime with `bash quick_check.sh`

**Option 3: Both (Recommended for long fetches)**
1. Run watchdog in background: `bash watchdog.sh`
2. When you want to see progress, run: `bash monitor.sh`
3. Best of both worlds!

---

## Process Information

- **Main process**: `compute_diy_dix_6y_optimized.py`
- **Client ID**: 80
- **Log file**: `logs/chunk_2020_FINAL_20260131_071207.log`
- **Output**: `data/dix/history/chunk_2020.csv`
- **Expected duration**: ~34 hours
- **Date range**: 2020-04-17 to 2020-12-31 (185 days)

---

## Troubleshooting

**Monitor shows "Waiting for progress data"**
- The fetch might be starting up or stuck
- Check if main process is running: `ps aux | grep compute_diy_dix`
- Check log file: `tail logs/chunk_2020_FINAL_20260131_071207.log`

**No Telegram alerts**
- Check credentials: `cat /etc/quantx/telegram.env`
- Test alert: Send yourself a test message using the bot token

**Watchdog not running**
- Check if it's running: `ps aux | grep watchdog`
- Check logs: `cat logs/watchdog_2020.log`
