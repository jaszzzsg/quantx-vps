#!/bin/bash
# Start completion notifier in background
# Sends Telegram message when chunk 2020 finishes

cd /root/projects/quantx_dix
source .venv/bin/activate

echo "Starting completion notifier in background..."
echo "You'll receive a Telegram message when chunk 2020 completes!"
echo ""

# Run in background
nohup python scripts/tools/notify_on_completion.py >> logs/completion_notifier.log 2>&1 &

NOTIFIER_PID=$!
echo "✓ Completion notifier started (PID: $NOTIFIER_PID)"
echo ""
echo "To check status: tail -f logs/completion_notifier.log"
echo "To stop: kill $NOTIFIER_PID"
echo ""

# Save PID
echo $NOTIFIER_PID > logs/completion_notifier.pid
