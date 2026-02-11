#!/bin/bash
# Watchdog for chunk 2020 fetch process
# Monitors the fetch and sends Telegram alert if it dies
# Run this in background or in a separate terminal

cd /root/projects/quantx_dix
source .venv/bin/activate

echo "Starting watchdog in background..."
echo "Logs will be saved to: logs/watchdog_2020.log"
echo ""

# Run watchdog and save output to log
nohup python scripts/tools/watchdog_2020.py >> logs/watchdog_2020.log 2>&1 &

WATCHDOG_PID=$!
echo "✓ Watchdog started (PID: $WATCHDOG_PID)"
echo ""
echo "To check status: tail -f logs/watchdog_2020.log"
echo "To stop: kill $WATCHDOG_PID"
echo ""

# Save PID for easy killing later
echo $WATCHDOG_PID > logs/watchdog_2020.pid
