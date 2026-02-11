#!/usr/bin/env python3
"""
Process watchdog for chunk 2020 fetch
Monitors the fetch process and sends Telegram alert if it dies unexpectedly
"""

import time
import os
import sys
import requests
from pathlib import Path
from datetime import datetime

# Configuration
PROCESS_NAME = "compute_diy_dix_6y_optimized.py"
CLIENT_ID = "80"  # The clientId used by chunk 2020
LOG_FILE = Path("/root/projects/quantx_dix/logs/chunk_2020_FINAL_20260131_071207.log")
CHECK_INTERVAL = 60  # Check every 60 seconds
TELEGRAM_ENV = Path("/etc/quantx/telegram.env")


def load_telegram_config():
    """Load Telegram credentials."""
    env = {}
    if TELEGRAM_ENV.exists():
        for line in TELEGRAM_ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

    return env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")


def send_telegram_alert(bot_token: str, chat_id: str, message: str):
    """Send Telegram notification."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "disable_web_page_preview": True
            },
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"Failed to send Telegram: {e}")
        return False


def is_process_running(process_name: str, client_id: str) -> bool:
    """Check if the fetch process is running."""
    try:
        import subprocess
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5
        )

        for line in result.stdout.splitlines():
            if process_name in line and f"clientId {client_id}" in line and "grep" not in line:
                return True
        return False
    except Exception as e:
        print(f"Error checking process: {e}")
        return False


def get_last_log_update():
    """Get the last modification time of the log file."""
    if LOG_FILE.exists():
        return LOG_FILE.stat().st_mtime
    return None


def parse_latest_progress():
    """Get latest progress from log."""
    if not LOG_FILE.exists():
        return None

    lines = LOG_FILE.read_text().splitlines()

    for line in reversed(lines):
        if "Day " in line and "/" in line and "%" in line:
            return line.strip()

    return None


def main():
    bot_token, chat_id = load_telegram_config()

    if not bot_token or not chat_id:
        print("ERROR: Telegram credentials not found in /etc/quantx/telegram.env")
        print("Watchdog will run but cannot send alerts!")
        sys.exit(1)

    print("=" * 70)
    print("🐕 Chunk 2020 Fetch Watchdog Started")
    print("=" * 70)
    print(f"Monitoring: {PROCESS_NAME} (clientId {CLIENT_ID})")
    print(f"Check interval: {CHECK_INTERVAL}s")
    print(f"Telegram alerts: Enabled ✓")
    print(f"Log file: {LOG_FILE}")
    print("\nWatchdog is running in the background...")
    print("Press Ctrl+C to stop\n")

    last_alert_time = 0
    alert_sent = False
    last_log_time = get_last_log_update()
    process_was_running = True

    try:
        while True:
            is_running = is_process_running(PROCESS_NAME, CLIENT_ID)
            current_time = time.time()

            # Check if log file is being updated
            current_log_time = get_last_log_update()
            log_stale = False
            if current_log_time and last_log_time:
                time_since_update = current_time - current_log_time
                if time_since_update > 600:  # 10 minutes
                    log_stale = True

            if not is_running:
                # Process died!
                if process_was_running and not alert_sent:
                    progress = parse_latest_progress()
                    message = (
                        f"🚨 ALERT: IBKR Chunk 2020 Fetch STOPPED!\n\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"Process: {PROCESS_NAME}\n"
                        f"Client ID: {CLIENT_ID}\n\n"
                        f"Last progress:\n{progress if progress else 'No data'}\n\n"
                        f"Please check your VPS!"
                    )

                    print(f"\n⚠️  PROCESS DIED! Sending Telegram alert...")
                    if send_telegram_alert(bot_token, chat_id, message):
                        print(f"✓ Alert sent successfully")
                        alert_sent = True
                        last_alert_time = current_time
                    else:
                        print(f"✗ Failed to send alert")

                print(f"\r⚠️  Process NOT running - Last check: {datetime.now().strftime('%H:%M:%S')}", end='')
                process_was_running = False

            elif log_stale:
                # Process running but log not updating
                if not alert_sent or (current_time - last_alert_time > 3600):  # Re-alert after 1 hour
                    progress = parse_latest_progress()
                    minutes_stale = int(time_since_update / 60)
                    message = (
                        f"⚠️ WARNING: IBKR Chunk 2020 Fetch may be STUCK!\n\n"
                        f"Process is running but log hasn't updated in {minutes_stale} minutes\n"
                        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                        f"Last progress:\n{progress if progress else 'No data'}\n\n"
                        f"Check if IBKR Gateway is running or if there's a network issue."
                    )

                    print(f"\n⚠️  LOG STALE! Sending Telegram alert...")
                    if send_telegram_alert(bot_token, chat_id, message):
                        print(f"✓ Alert sent successfully")
                        alert_sent = True
                        last_alert_time = current_time

                print(f"\r⚠️  Process running but log stale ({minutes_stale}m) - {datetime.now().strftime('%H:%M:%S')}", end='')

            else:
                # All good!
                if not process_was_running:
                    # Process restarted
                    message = f"✅ Chunk 2020 fetch process restarted at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    send_telegram_alert(bot_token, chat_id, message)
                    alert_sent = False

                print(f"\r✓ Process running - Last check: {datetime.now().strftime('%H:%M:%S')} ", end='')
                process_was_running = True
                alert_sent = False
                last_log_time = current_log_time

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("Watchdog stopped by user")
        print("=" * 70)


if __name__ == "__main__":
    main()
