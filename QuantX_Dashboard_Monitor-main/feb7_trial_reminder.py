#!/usr/bin/env python3
"""
Paper Trading Trial Reminder - Feb 7, 2026

This script sends a Telegram reminder on Feb 7, 2026 to:
1. Review paper trading trial results (Feb 2-6)
2. Restore RF_THRESHOLD from 0.10 back to 0.60

Schedule this script to run on Feb 7, 2026:
    crontab -e
    0 9 * * * /root/odte_strategy/venv/bin/python /root/projects/QuantX_Dashboard_Monitor-main/feb7_trial_reminder.py

Or run manually:
    /root/odte_strategy/venv/bin/python /root/projects/QuantX_Dashboard_Monitor-main/feb7_trial_reminder.py
"""

import os
import sys
import json
from datetime import datetime, date
from zoneinfo import ZoneInfo

BASE_PATH = "/root/projects/QuantX_Dashboard_Monitor-main"
sys.path.append(BASE_PATH)

from utils.tg_notify import tg_send

# Configuration
TRIAL_END_DATE = date(2026, 2, 6)
REMINDER_DATE = date(2026, 2, 7)
ET = ZoneInfo("America/New_York")

def load_trial_config():
    """Load the trial configuration backup"""
    config_file = f"{BASE_PATH}/PAPER_TRIAL_CONFIG_BACKUP.json"
    if not os.path.isfile(config_file):
        return None
    with open(config_file, "r") as f:
        return json.load(f)

def count_trades_in_log(log_file):
    """Count successful trade entries in log"""
    if not os.path.isfile(log_file):
        return 0

    count = 0
    with open(log_file, "r") as f:
        for line in f:
            if "TRADE_ENTER" in line:
                count += 1
    return count

def get_trial_summary():
    """Generate trial summary statistics"""
    bear_log = f"{BASE_PATH}/strategies_runner/logs/001_alpha_spx_1330_0dte_bear_call/trade_log.csv"
    bull_log = f"{BASE_PATH}/strategies_runner/logs/002_alpha_spx_1330_0dte_bull_put/trade_log.csv"

    bear_trades = count_trades_in_log(bear_log)
    bull_trades = count_trades_in_log(bull_log)

    return {
        "bear_call_trades": bear_trades,
        "bull_put_trades": bull_trades,
        "total_trades": bear_trades + bull_trades
    }

def send_reminder():
    """Send Telegram reminder on Feb 7, 2026"""
    today = datetime.now(ET).date()

    # Check if today is the reminder date
    if today != REMINDER_DATE:
        print(f"Not yet Feb 7, 2026. Today is {today}. Exiting.")
        return

    # Load config
    config = load_trial_config()
    if not config:
        print("ERROR: Trial config file not found!")
        return

    # Get trial summary
    summary = get_trial_summary()

    # Check if already restored
    if config.get("restore_log", {}).get("restored", False):
        restored_date = config["restore_log"].get("restored_date")
        msg = (
            f"⚠️ REMINDER: Paper Trial Cleanup\n"
            f"\n"
            f"RF_THRESHOLD was already restored on {restored_date}.\n"
            f"No action needed.\n"
            f"\n"
            f"Trial Summary (Feb 2-6):\n"
            f"  • Bear Call trades: {summary['bear_call_trades']}\n"
            f"  • Bull Put trades: {summary['bull_put_trades']}\n"
            f"  • Total trades: {summary['total_trades']}\n"
        )
        tg_send(msg)
        print("Reminder sent (already restored)")
        return

    # Build reminder message
    msg = (
        f"🔔 PAPER TRIAL REMINDER - ACTION REQUIRED\n"
        f"\n"
        f"📅 Trial Period: Feb 2-6, 2026 (ENDED)\n"
        f"📊 Results Summary:\n"
        f"  • Bear Call trades: {summary['bear_call_trades']}\n"
        f"  • Bull Put trades: {summary['bull_put_trades']}\n"
        f"  • Total trades: {summary['total_trades']}\n"
        f"\n"
        f"⚠️ ACTION REQUIRED:\n"
        f"1️⃣ Review trial results in logs:\n"
        f"   • Bear Call: logs/001_alpha_spx_1330_0dte_bear_call/trade_log.csv\n"
        f"   • Bull Put: logs/002_alpha_spx_1330_0dte_bull_put/trade_log.csv\n"
        f"\n"
        f"2️⃣ RESTORE RF_THRESHOLD:\n"
        f"   File: strategies_runner/001_alpha_spx_1330_0dte_bear_call.py\n"
        f"   Line: 48-51\n"
        f"   Change: RF_THRESHOLD = 0.10 → 0.60\n"
        f"\n"
        f"   ORIGINAL VALUE: 0.60 (60%)\n"
        f"   CURRENT VALUE: 0.10 (10%) ⚠️\n"
        f"\n"
        f"3️⃣ Verify restoration:\n"
        f"   Run: grep RF_THRESHOLD strategies_runner/001_*.py\n"
        f"   Should show: RF_THRESHOLD = 0.60\n"
        f"\n"
        f"4️⃣ Update restore log:\n"
        f"   Edit: PAPER_TRIAL_CONFIG_BACKUP.json\n"
        f"   Set: restore_log.restored = true\n"
        f"\n"
        f"📋 Detailed config: PAPER_TRIAL_CONFIG_BACKUP.json\n"
        f"\n"
        f"⏰ Time: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S ET')}\n"
    )

    # Send reminder
    try:
        tg_send(msg)
        print(f"✅ Reminder sent successfully at {datetime.now(ET)}")

        # Log the reminder
        log_file = f"{BASE_PATH}/feb7_reminder.log"
        with open(log_file, "a") as f:
            f.write(f"{datetime.now(ET).isoformat()} - Reminder sent. Trades: {summary['total_trades']}\n")

    except Exception as e:
        print(f"❌ Failed to send reminder: {e}")

if __name__ == "__main__":
    send_reminder()
