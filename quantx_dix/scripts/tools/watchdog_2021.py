#!/usr/bin/env python3
"""
Watchdog for chunk 2021 fetch - monitors process and sends Telegram alerts
"""

import time
import os
import requests
from pathlib import Path
from datetime import datetime

LOG_FILE = Path("/root/projects/quantx_dix/logs/chunk_20210104_20211231_20260131_144347.log")
PID_FILE = Path("/root/projects/quantx_dix/logs/watchdog_2021.pid")
TELEGRAM_ENV = Path("/etc/quantx/telegram.env")
CHECK_INTERVAL = 60  # Check every 60 seconds

def load_telegram_env():
    """Load Telegram credentials."""
    env = {}
    if TELEGRAM_ENV.exists():
        for line in TELEGRAM_ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env

def send_telegram(message: str):
    """Send Telegram notification."""
    env = load_telegram_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print(f"[WARN] No Telegram credentials configured")
        return False

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": True
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")
        return False

def is_process_running() -> bool:
    """Check if the fetch process is running."""
    try:
        result = os.popen('ps aux | grep "compute_diy_dix_6y_optimized" | grep "2021" | grep -v grep').read()
        return bool(result.strip())
    except:
        return False

def get_last_log_update_time() -> float:
    """Get last modification time of log file."""
    if LOG_FILE.exists():
        return LOG_FILE.stat().st_mtime
    return 0

def main():
    # Save PID
    PID_FILE.write_text(str(os.getpid()))

    # Send startup notification
    send_telegram(f"🔍 Watchdog Started for Chunk 2021\n\nMonitoring fetch process.\nYou'll be alerted if anything goes wrong!")

    print(f"[{datetime.now()}] Watchdog started for chunk 2021")

    last_log_time = get_last_log_update_time()
    alert_sent = False

    try:
        while True:
            # Check if process is running
            if not is_process_running():
                if not alert_sent:
                    send_telegram(f"🚨 ALERT: Chunk 2021 Fetch Process DIED!\n\nProcess stopped unexpectedly.\nPlease check the logs and restart.")
                    alert_sent = True
                    print(f"[{datetime.now()}] ALERT: Process died!")
            else:
                # Check if log is being updated
                current_log_time = get_last_log_update_time()
                if current_log_time > last_log_time:
                    last_log_time = current_log_time
                    alert_sent = False  # Reset alert
                elif (time.time() - last_log_time) > 600:  # 10 minutes
                    if not alert_sent:
                        send_telegram(f"⚠️ WARNING: Chunk 2021 Fetch May Be Stuck\n\nLog file hasn't been updated in 10+ minutes.\nProcess is running but may be hung.")
                        alert_sent = True
                        print(f"[{datetime.now()}] WARNING: Log not updating")

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n[{datetime.now()}] Watchdog stopped")
        PID_FILE.unlink(missing_ok=True)

if __name__ == "__main__":
    main()
