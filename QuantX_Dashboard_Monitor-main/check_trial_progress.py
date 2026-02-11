#!/usr/bin/env python3
"""
Paper Trading Trial Progress Checker

Run this daily during the trial period (Feb 2-6, 2026) to monitor:
- Trades placed (Bear Call vs Bull Put)
- Trade details (strikes, credits, status)
- Errors or skips
- Current market conditions

Usage:
    /root/odte_strategy/venv/bin/python /root/projects/QuantX_Dashboard_Monitor-main/check_trial_progress.py
"""

import os
import sys
import json
import csv
from datetime import datetime, date
from zoneinfo import ZoneInfo
from collections import defaultdict

BASE_PATH = "/root/projects/QuantX_Dashboard_Monitor-main"
ET = ZoneInfo("America/New_York")

TRIAL_START = date(2026, 2, 2)
TRIAL_END = date(2026, 2, 6)

def print_header(title):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def load_arm_regime():
    """Load current ARM regime"""
    arm_file = "/root/projects/quantx_arm/state/regime_state.json"
    try:
        with open(arm_file, "r") as f:
            data = json.load(f)
        return data.get("regime", "NA"), data.get("asof_date", "Unknown")
    except:
        return "NA", "Unknown"

def load_rf_prob():
    """Load current RF probability"""
    rf_file = "/root/odte_strategy/data/rf_daily_predictions.csv"
    try:
        with open(rf_file, "r") as f:
            lines = f.readlines()
        if len(lines) > 1:
            last_line = lines[-1].strip().split(",")
            return float(last_line[1]) if len(last_line) > 1 else None
    except:
        return None

def parse_log_file(log_file):
    """Parse strategy log file and return stats"""
    if not os.path.isfile(log_file):
        return {
            "total_entries": 0,
            "trade_enters": 0,
            "skips": defaultdict(int),
            "errors": 0,
            "recent_trades": []
        }

    stats = {
        "total_entries": 0,
        "trade_enters": 0,
        "skips": defaultdict(int),
        "errors": 0,
        "recent_trades": []
    }

    try:
        with open(log_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                stats["total_entries"] += 1
                action = row.get("action", "")

                if action == "TRADE_ENTER":
                    stats["trade_enters"] += 1
                    try:
                        details = json.loads(row.get("details", "{}"))
                        stats["recent_trades"].append({
                            "timestamp": row.get("timestamp_utc", ""),
                            "regime": row.get("regime", ""),
                            "rf_prob": row.get("rf_prob", ""),
                            "details": details
                        })
                    except:
                        pass

                elif action.startswith("SKIP"):
                    stats["skips"][action] += 1

                elif action == "ERROR":
                    stats["errors"] += 1

    except Exception as e:
        print(f"Warning: Error parsing {log_file}: {e}")

    return stats

def check_trial_status():
    """Main trial status checker"""
    today = datetime.now(ET).date()

    print_header("PAPER TRADING TRIAL PROGRESS")
    print(f"Current Date: {today.strftime('%A, %B %d, %Y')}")
    print(f"Current Time: {datetime.now(ET).strftime('%I:%M:%S %p ET')}")
    print()

    # Trial period status
    if today < TRIAL_START:
        print(f"⏳ Trial hasn't started yet. Starts: {TRIAL_START}")
        days_until = (TRIAL_START - today).days
        print(f"   Days until trial: {days_until}")
    elif today > TRIAL_END:
        print(f"✅ Trial period ended on {TRIAL_END}")
        print(f"   ⚠️  REMEMBER TO RESTORE RF_THRESHOLD TO 0.60!")
    else:
        day_num = (today - TRIAL_START).days + 1
        print(f"🔄 Trial in progress - Day {day_num} of 5")
        print(f"   Period: {TRIAL_START} to {TRIAL_END}")

    # Market conditions
    print_header("CURRENT MARKET CONDITIONS")
    regime, regime_date = load_arm_regime()
    rf_prob = load_rf_prob()

    print(f"ARM Regime: {regime} (as of {regime_date})")
    if rf_prob:
        print(f"RF Probability: {rf_prob:.4f} ({rf_prob*100:.2f}%)")
        print(f"  Original Threshold: 0.60 (60%)")
        print(f"  Trial Threshold: 0.10 (10%)")
        print(f"  Would Pass Original: {'✅ YES' if rf_prob >= 0.60 else '❌ NO'}")
        print(f"  Passes Trial: {'✅ YES' if rf_prob >= 0.10 else '❌ NO'}")
    else:
        print(f"RF Probability: Not available")

    # Bear Call (001) Stats
    print_header("BEAR CALL STRATEGY (001)")
    bear_log = f"{BASE_PATH}/strategies_runner/logs/001_alpha_spx_1330_0dte_bear_call/trade_log.csv"
    bear_stats = parse_log_file(bear_log)

    print(f"Total Log Entries: {bear_stats['total_entries']}")
    print(f"Trades Placed: {bear_stats['trade_enters']} 📊")
    print(f"Errors: {bear_stats['errors']}")
    print(f"\nSkip Reasons:")
    if bear_stats['skips']:
        for skip_type, count in bear_stats['skips'].items():
            print(f"  • {skip_type}: {count}")
    else:
        print(f"  (none)")

    if bear_stats['recent_trades']:
        print(f"\nRecent Trades:")
        for i, trade in enumerate(bear_stats['recent_trades'][-3:], 1):
            details = trade['details']
            print(f"\n  Trade {i}:")
            print(f"    Time: {trade['timestamp']}")
            print(f"    Regime: {trade['regime']}, RF: {trade['rf_prob']}")
            print(f"    Strikes: {details.get('short_call', '?')}/{details.get('long_call', '?')}")
            print(f"    Credit: ${details.get('credit', 0):.2f}")
            print(f"    SPX: ${details.get('spx_px', 0):.2f}")
            print(f"    Status: {details.get('status', 'Unknown')}")

    # Bull Put (002) Stats
    print_header("BULL PUT STRATEGY (002)")
    bull_log = f"{BASE_PATH}/strategies_runner/logs/002_alpha_spx_1330_0dte_bull_put/trade_log.csv"
    bull_stats = parse_log_file(bull_log)

    print(f"Total Log Entries: {bull_stats['total_entries']}")
    print(f"Trades Placed: {bull_stats['trade_enters']} 📊")
    print(f"Errors: {bull_stats['errors']}")
    print(f"\nSkip Reasons:")
    if bull_stats['skips']:
        for skip_type, count in bull_stats['skips'].items():
            print(f"  • {skip_type}: {count}")
    else:
        print(f"  (none)")

    if bull_stats['recent_trades']:
        print(f"\nRecent Trades:")
        for i, trade in enumerate(bull_stats['recent_trades'][-3:], 1):
            details = trade['details']
            print(f"\n  Trade {i}:")
            print(f"    Time: {trade['timestamp']}")
            print(f"    Regime: {trade['regime']}")
            print(f"    Strikes: {details.get('short_put', '?')}/{details.get('long_put', '?')}")
            print(f"    Credit: ${details.get('credit', 0):.2f}")
            print(f"    SPX: ${details.get('spx_px', 0):.2f}")
            print(f"    Status: {details.get('status', 'Unknown')}")

    # Summary
    print_header("TRIAL SUMMARY")
    total_trades = bear_stats['trade_enters'] + bull_stats['trade_enters']
    total_skips = sum(bear_stats['skips'].values()) + sum(bull_stats['skips'].values())
    total_errors = bear_stats['errors'] + bull_stats['errors']

    print(f"Total Trades Placed: {total_trades}")
    print(f"  • Bear Call: {bear_stats['trade_enters']}")
    print(f"  • Bull Put: {bull_stats['trade_enters']}")
    print(f"\nTotal Skips: {total_skips}")
    print(f"Total Errors: {total_errors}")

    # Expected behavior
    print_header("EXPECTED BEHAVIOR DURING TRIAL")
    print("✓ Bear Call should trade if:")
    print("  • Time is 1:30-3:10 PM ET (Mon-Fri)")
    print("  • RF probability >= 0.10 (lowered from 0.60)")
    print("  • IB Gateway connected")
    print("  • Mid-market credit >= $1.00")
    print()
    print("✓ Bull Put should trade if:")
    print("  • Bear Call hasn't traded today")
    print("  • ARM regime != R3")
    print("  • Time is 1:30-3:10 PM ET (Mon-Fri)")
    print("  • IB Gateway connected")
    print("  • Mid-market credit >= $1.00")
    print()
    print("✓ Mutual exclusivity: Only ONE strategy trades per day")
    print("  (Bear Call has priority)")

    # Recommendations
    print_header("NEXT STEPS")
    if total_trades == 0 and today >= TRIAL_START:
        print("⚠️  No trades placed yet. Check:")
        print("   1. Is IB Gateway running on port 4002?")
        print("   2. Are scripts running during 1:30-3:10 PM ET?")
        print("   3. Check Telegram for skip notifications")
        print("   4. Review error logs above")
    elif total_trades > 0:
        print("✅ Trades are being placed successfully!")
        print("   Continue monitoring daily until Feb 6")
        print("   Review trade details in IB paper account")

    if today >= TRIAL_END:
        print("\n⚠️  TRIAL ENDED - RESTORE RF_THRESHOLD:")
        print("   1. Edit strategies_runner/001_alpha_spx_1330_0dte_bear_call.py")
        print("   2. Change RF_THRESHOLD = 0.10 → 0.60")
        print("   3. Remove trial comments")
        print("   4. Update PAPER_TRIAL_CONFIG_BACKUP.json restore_log")

    print("\n" + "=" * 70)
    print("Report generated:", datetime.now(ET).strftime("%Y-%m-%d %I:%M:%S %p ET"))
    print("=" * 70 + "\n")

if __name__ == "__main__":
    check_trial_status()
