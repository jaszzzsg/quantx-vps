#!/usr/bin/env python3
"""
Trading Strategy Component Diagnostic Tool
Tests all components of the 0DTE Bear Call/Bull Put strategies
WITHOUT placing actual trades

Usage:
    /root/odte_strategy/venv/bin/python test_strategy_components.py

Author: Diagnostic Script
Date: 2026-01-31
"""

import os
import sys
import json
from datetime import datetime
from zoneinfo import ZoneInfo

# Add paths
BASE_PATH = "/root/projects/QuantX_Dashboard_Monitor-main"
sys.path.append(BASE_PATH)

# Test results
results = {
    "timestamp": datetime.now().isoformat(),
    "tests": []
}

def test_result(name, passed, message, details=None):
    """Record a test result"""
    emoji = "✅" if passed else "❌"
    results["tests"].append({
        "name": name,
        "passed": passed,
        "message": message,
        "details": details or {}
    })
    print(f"{emoji} {name}: {message}")
    if details:
        for k, v in details.items():
            print(f"   {k}: {v}")
    print()

# ============================================================
# TEST 1: Time Zone & Time Window Logic
# ============================================================
print("=" * 60)
print("TEST 1: Time Zone & Time Window")
print("=" * 60)

try:
    ET = ZoneInfo("America/New_York")
    now_et = datetime.now(ET)
    hour, minute = now_et.hour, now_et.minute

    # Check if in entry window (1:30 PM - 3:10 PM ET)
    in_window = ((hour > 13) or (hour == 13 and minute >= 30)) and \
                ((hour < 15) or (hour == 15 and minute <= 10))

    test_result(
        "Time Zone Configuration",
        True,
        f"Time: {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        {
            "In Entry Window (1:30-3:10 PM ET)": "Yes" if in_window else "No",
            "Current Hour": hour,
            "Current Minute": minute,
            "Day of Week": now_et.strftime("%A")
        }
    )
except Exception as e:
    test_result("Time Zone Configuration", False, str(e))

# ============================================================
# TEST 2: ARM Regime State
# ============================================================
print("=" * 60)
print("TEST 2: ARM Regime State")
print("=" * 60)

ARM_JSON = "/root/projects/quantx_arm/state/regime_state.json"

try:
    if not os.path.isfile(ARM_JSON):
        test_result("ARM Regime File", False, "File not found", {"path": ARM_JSON})
    else:
        with open(ARM_JSON, "r") as f:
            arm_data = json.load(f)

        regime = arm_data.get("regime", "NA")
        asof_date = arm_data.get("asof_date", "Unknown")

        # Check if data is fresh (today or yesterday)
        today = datetime.now(ET).strftime("%Y-%m-%d")
        is_fresh = asof_date >= today or asof_date == "Unknown"

        test_result(
            "ARM Regime Loading",
            True,
            f"Regime: {regime}",
            {
                "As-of Date": asof_date,
                "Data Fresh": "Yes" if is_fresh else f"No (stale since {asof_date})",
                "VIX Close": arm_data.get("market", {}).get("vix_close", "N/A"),
                "Flags": str(arm_data.get("flags", {}))
            }
        )
except Exception as e:
    test_result("ARM Regime Loading", False, str(e))

# ============================================================
# TEST 3: RF Daily Predictions
# ============================================================
print("=" * 60)
print("TEST 3: RF Daily Predictions")
print("=" * 60)

RF_CSV = "/root/odte_strategy/data/rf_daily_predictions.csv"

try:
    import pandas as pd

    if not os.path.isfile(RF_CSV):
        test_result("RF Predictions File", False, "File not found", {"path": RF_CSV})
    else:
        df = pd.read_csv(RF_CSV)

        # Find date and prob columns
        date_cols = [c for c in df.columns if "date" in c.lower()]
        prob_cols = [c for c in df.columns if "prob" in c.lower()]

        if not date_cols or not prob_cols:
            test_result("RF Predictions Format", False, "Missing date or prob columns")
        else:
            date_col = date_cols[0]
            prob_col = prob_cols[0]

            # Get most recent prediction
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
            latest = df.iloc[-1]

            rf_date = latest[date_col]
            rf_prob = float(latest[prob_col])
            rf_threshold = 0.60

            test_result(
                "RF Predictions Loading",
                True,
                f"Probability: {rf_prob:.4f} ({rf_prob*100:.2f}%)",
                {
                    "Date": rf_date,
                    "Threshold": f"{rf_threshold} (60%)",
                    "Passes Threshold": "Yes ✅" if rf_prob >= rf_threshold else "No ❌",
                    "Decision": latest.get("decision", "N/A")
                }
            )
except Exception as e:
    test_result("RF Predictions Loading", False, str(e))

# ============================================================
# TEST 4: Logging System
# ============================================================
print("=" * 60)
print("TEST 4: Logging System")
print("=" * 60)

LOG_DIRS = [
    f"{BASE_PATH}/strategies_runner/logs/001_alpha_spx_1330_0dte_bear_call",
    f"{BASE_PATH}/strategies_runner/logs/002_alpha_spx_1330_0dte_bull_put",
]

for log_dir in LOG_DIRS:
    strategy_name = os.path.basename(log_dir)
    log_file = f"{log_dir}/trade_log.csv"

    try:
        if not os.path.isdir(log_dir):
            test_result(f"Log Directory ({strategy_name})", False, "Directory not found")
        elif not os.path.isfile(log_file):
            test_result(f"Log File ({strategy_name})", False, "Log file not found")
        else:
            # Read last few lines
            with open(log_file, "r") as f:
                lines = f.readlines()

            num_entries = len(lines) - 1  # Subtract header
            last_entry = lines[-1].strip() if len(lines) > 1 else "None"

            test_result(
                f"Log File ({strategy_name})",
                True,
                f"{num_entries} log entries found",
                {
                    "File Size": f"{os.path.getsize(log_file)} bytes",
                    "Last Entry": last_entry[:80] + "..." if len(last_entry) > 80 else last_entry
                }
            )
    except Exception as e:
        test_result(f"Log System ({strategy_name})", False, str(e))

# ============================================================
# TEST 5: IB Gateway Connection
# ============================================================
print("=" * 60)
print("TEST 5: IB Gateway Connection")
print("=" * 60)

try:
    from ib_insync import IB
    from utils.client_id_manager import get_or_allocate_client_id

    client_id = get_or_allocate_client_id("diagnostic_test", role="test")

    ib = IB()
    ib.connect("127.0.0.1", 4002, clientId=client_id, timeout=10)

    accounts = ib.managedAccounts()

    test_result(
        "IB Gateway Connection",
        True,
        "Connected successfully",
        {
            "Host": "127.0.0.1",
            "Port": 4002,
            "Client ID": client_id,
            "Accounts": ", ".join(accounts) if accounts else "None"
        }
    )

    # Keep connection for next test
    ib_connected = ib

except Exception as e:
    test_result("IB Gateway Connection", False, str(e))
    ib_connected = None

# ============================================================
# TEST 6: Market Data (SPX Price)
# ============================================================
print("=" * 60)
print("TEST 6: Market Data Access (SPX)")
print("=" * 60)

if ib_connected:
    try:
        from ib_insync import Index
        import math

        spx = Index("SPX", "CBOE", "USD")
        ib_connected.qualifyContracts(spx)

        ticker = ib_connected.reqMktData(spx, "", False, False)
        ib_connected.sleep(3)

        price = ticker.last or ticker.close or ticker.marketPrice()

        if price and not math.isnan(price):
            test_result(
                "SPX Market Data",
                True,
                f"SPX Price: ${price:.2f}",
                {
                    "Last": ticker.last,
                    "Close": ticker.close,
                    "Bid": ticker.bid,
                    "Ask": ticker.ask
                }
            )
        else:
            test_result(
                "SPX Market Data",
                False,
                "Price unavailable (market closed?)",
                {"Ticker": str(ticker)}
            )
    except Exception as e:
        test_result("SPX Market Data", False, str(e))
else:
    test_result("SPX Market Data", False, "Skipped (no IB connection)")

# ============================================================
# TEST 7: Option Chain Availability (0DTE SPXW)
# ============================================================
print("=" * 60)
print("TEST 7: Option Chain (0DTE SPXW)")
print("=" * 60)

if ib_connected:
    try:
        from ib_insync import Index

        spx = Index("SPX", "CBOE", "USD")
        ib_connected.qualifyContracts(spx)

        chains = ib_connected.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)

        # Find SPXW chain
        spxw_chain = next((c for c in chains if getattr(c, "tradingClass", "") == "SPXW"), None)

        if spxw_chain:
            today = datetime.now(ET).strftime("%Y%m%d")
            has_today_expiry = today in spxw_chain.expirations

            test_result(
                "SPXW Option Chain",
                True,
                f"Found {len(spxw_chain.expirations)} expirations",
                {
                    "Trading Class": spxw_chain.tradingClass,
                    "Today's Date": today,
                    "0DTE Available": "Yes ✅" if has_today_expiry else "No ❌",
                    "Next 3 Expiries": ", ".join(list(spxw_chain.expirations)[:3])
                }
            )
        else:
            test_result("SPXW Option Chain", False, "SPXW chain not found")

    except Exception as e:
        test_result("SPXW Option Chain", False, str(e))
else:
    test_result("SPXW Option Chain", False, "Skipped (no IB connection)")

# ============================================================
# TEST 8: Telegram Notifications
# ============================================================
print("=" * 60)
print("TEST 8: Telegram Notification System")
print("=" * 60)

try:
    # Check environment variables first
    tg_token = os.environ.get("TG_BOT_TOKEN", "")
    tg_chat = os.environ.get("TG_CHAT_ID", "")

    if not tg_token or not tg_chat:
        test_result(
            "Telegram Configuration",
            False,
            "Environment variables not set",
            {
                "TG_BOT_TOKEN": "Set" if tg_token else "NOT SET ❌",
                "TG_CHAT_ID": "Set" if tg_chat else "NOT SET ❌"
            }
        )
    else:
        from utils.tg_notify import tg_send

        # Send test message
        test_msg = f"🧪 Diagnostic Test\nTime: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S ET')}\nStatus: Testing notification system"

        try:
            tg_send(test_msg)
            test_result(
                "Telegram Notifications",
                True,
                "Test message sent - check your Telegram!",
                {
                    "Bot Token": tg_token[:10] + "...",
                    "Chat ID": tg_chat
                }
            )
        except Exception as e:
            test_result("Telegram Notifications", False, f"Send failed: {str(e)}")

except Exception as e:
    test_result("Telegram Notifications", False, str(e))

# ============================================================
# Disconnect IB
# ============================================================
if ib_connected:
    try:
        ib_connected.disconnect()
    except:
        pass

# ============================================================
# SUMMARY
# ============================================================
print("=" * 60)
print("DIAGNOSTIC SUMMARY")
print("=" * 60)

total_tests = len(results["tests"])
passed_tests = sum(1 for t in results["tests"] if t["passed"])
failed_tests = total_tests - passed_tests

print(f"\nTotal Tests: {total_tests}")
print(f"✅ Passed: {passed_tests}")
print(f"❌ Failed: {failed_tests}")
print(f"\nSuccess Rate: {(passed_tests/total_tests*100):.1f}%")

if failed_tests > 0:
    print("\n⚠️  FAILED TESTS:")
    for test in results["tests"]:
        if not test["passed"]:
            print(f"  - {test['name']}: {test['message']}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)

# Save results to file
output_file = f"{BASE_PATH}/diagnostic_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(output_file, "w") as f:
    json.dump(results, f, indent=2)

print(f"\nDetailed results saved to: {output_file}")
