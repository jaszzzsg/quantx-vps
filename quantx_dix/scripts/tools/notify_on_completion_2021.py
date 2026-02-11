#!/usr/bin/env python3
"""
Completion notifier for chunk 2021 - sends Telegram when fetch completes
"""

import time
import os
import requests
from pathlib import Path
from datetime import datetime

LOG_FILE = Path("/root/projects/quantx_dix/logs/chunk_20210104_20211231_20260131_144347.log")
OUTPUT_FILE = Path("/root/projects/quantx_dix/data/dix/history/chunk_2021.csv")
TELEGRAM_ENV = Path("/etc/quantx/telegram.env")
CHECK_INTERVAL = 300  # Check every 5 minutes

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

def is_fetch_complete() -> bool:
    """Check if the fetch is complete."""
    if not LOG_FILE.exists():
        return False

    try:
        lines = LOG_FILE.read_text().splitlines()
        for line in reversed(lines[-20:]):
            if "[100%] DONE!" in line or "DONE! Saved:" in line:
                return True
    except:
        pass
    return False

def get_file_stats():
    """Get output file statistics."""
    if not OUTPUT_FILE.exists():
        return None

    size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
    try:
        with open(OUTPUT_FILE) as f:
            lines = sum(1 for _ in f)
        return f"{lines:,} rows, {size_mb:.1f} MB"
    except:
        return f"{size_mb:.1f} MB"

def main():
    print(f"[{datetime.now()}] Completion notifier started for chunk 2021")

    # Send startup notification
    send_telegram(f"📬 Completion Notifier Started\n\nMonitoring chunk 2021 fetch.\nYou'll get a notification when it completes!")

    try:
        while True:
            if is_fetch_complete():
                stats = get_file_stats()
                completion_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                message = f"""🎉 CHUNK 2021 FETCH COMPLETED!

Finished at: {completion_time}

Output: chunk_2021.csv
Stats: {stats}

✅ Ready to start chunk 2022!"""

                send_telegram(message)
                print(f"[{datetime.now()}] Completion notification sent!")
                break

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print(f"\n[{datetime.now()}] Completion notifier stopped")

if __name__ == "__main__":
    main()
