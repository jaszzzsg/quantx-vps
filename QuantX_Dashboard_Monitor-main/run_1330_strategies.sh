#!/bin/bash
# Strategy runner for 1:30 PM ET entry window
# Runs Bear Call (001) first, then Bull Put (002) if Bear didn't trade

cd /root/projects/QuantX_Dashboard_Monitor-main

# Load paper trading env (Telegram creds, IB config, RF threshold)
set -a
# shellcheck source=/root/odte_strategy/.env.paper
source /root/odte_strategy/.env.paper
set +a

# tg_notify.py uses TG_BOT_TOKEN / TG_CHAT_ID — map from TELEGRAM_* if needed
export TG_BOT_TOKEN="${TG_BOT_TOKEN:-${TELEGRAM_BOT_TOKEN}}"
export TG_CHAT_ID="${TG_CHAT_ID:-${TELEGRAM_CHAT_ID}}"

LOG_DIR="strategies_runner/logs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
WRAPPER_LOG="$LOG_DIR/strategy_wrapper_${TIMESTAMP}.log"

mkdir -p "$LOG_DIR"

{
    echo "=========================================="
    echo "Strategy Runner - $(date)"
    echo "=========================================="

    # Run Bear Call (001)
    echo "[$(date)] Starting Bear Call strategy (001)..."
    /root/odte_strategy/venv/bin/python strategies_runner/001_alpha_spx_1330_0dte_bear_call.py
    echo "[$(date)] Bear Call exited with code: $?"

    # Run Bull Put (002) - it will check if Bear Call already traded
    echo "[$(date)] Starting Bull Put strategy (002)..."
    /root/odte_strategy/venv/bin/python strategies_runner/002_alpha_spx_1330_0dte_bull_put.py
    echo "[$(date)] Bull Put exited with code: $?"

    echo "[$(date)] Strategy execution complete"
    echo "=========================================="
} >> "$WRAPPER_LOG" 2>&1

# Always exit 0 so cron doesn't send error emails
exit 0
