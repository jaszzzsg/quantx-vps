#!/bin/bash
# Start all monitoring for chunk 2021

cd /root/projects/quantx_dix
source .venv/bin/activate

echo "Starting monitoring for Chunk 2021..."
echo ""

# Start watchdog
echo "1. Starting watchdog..."
nohup python scripts/tools/watchdog_2021.py > logs/watchdog_2021.log 2>&1 &
WATCHDOG_PID=$!
echo "   ✓ Watchdog started (PID: $WATCHDOG_PID)"

# Start completion notifier
echo "2. Starting completion notifier..."
nohup python scripts/tools/notify_on_completion_2021.py > logs/completion_notifier_2021.log 2>&1 &
NOTIFIER_PID=$!
echo "   ✓ Completion notifier started (PID: $NOTIFIER_PID)"

echo ""
echo "======================================"
echo "✅ All monitoring active for Chunk 2021"
echo "======================================"
echo ""
echo "You'll receive Telegram alerts for:"
echo "  • Process crashes"
echo "  • Process stuck/frozen"
echo "  • Completion (ready for chunk 2022)"
echo ""
echo "To view live progress:"
echo "  python scripts/tools/live_monitor_2021.py"
echo ""
echo "To check status:"
echo "  ps aux | grep '2021' | grep -E '(watchdog|notify)'"
