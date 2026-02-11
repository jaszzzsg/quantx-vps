#!/usr/bin/env python3
"""
Monitors chunk 2020 fetch and sends Telegram notification when complete
Runs in background until the fetch finishes
"""

import time
import requests
from pathlib import Path
from datetime import datetime

# Configuration
LOG_FILE = Path("/root/projects/quantx_dix/logs/chunk_2020_FINAL_20260131_071207.log")
OUTPUT_FILE = Path("/root/projects/quantx_dix/data/dix/history/chunk_2020.csv")
TELEGRAM_ENV = Path("/etc/quantx/telegram.env")
CHECK_INTERVAL = 300  # Check every 5 minutes
PROCESS_NAME = "compute_diy_dix_6y_optimized.py"


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


def send_telegram(bot_token: str, chat_id: str, message: str):
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


def is_process_running() -> bool:
    """Check if fetch process is still running."""
    import subprocess
    try:
        result = subprocess.run(
            ["ps", "aux"],
            capture_output=True,
            text=True,
            timeout=5
        )
        for line in result.stdout.splitlines():
            if PROCESS_NAME in line and "clientId 80" in line and "grep" not in line:
                return True
        return False
    except:
        return False


def get_latest_progress():
    """Parse latest progress from log."""
    if not LOG_FILE.exists():
        return None

    lines = LOG_FILE.read_text().splitlines()

    for line in reversed(lines):
        if "Day " in line and "/" in line and "ETA:" in line:
            try:
                parts = line.split()
                # Get day numbers
                day_part = [p for p in parts if '/' in p][0]
                current, total = map(int, day_part.split('/'))

                # Get percentage
                pct_str = None
                for p in parts:
                    if '%]' in p:
                        pct_str = p.strip('[]%')
                        break
                pct = int(pct_str) if pct_str else 0

                # Get date
                ymd = [p for p in parts if len(p) == 8 and p.isdigit()][0]

                return {
                    'percent': pct,
                    'current_day': current,
                    'total_days': total,
                    'date': ymd,
                    'line': line.strip()
                }
            except:
                continue

    return None


def check_completion():
    """Check if fetch is complete."""
    # Method 1: Process no longer running AND output file exists
    if not is_process_running() and OUTPUT_FILE.exists():
        return True

    # Method 2: Progress shows 100%
    progress = get_latest_progress()
    if progress and progress['current_day'] >= progress['total_days']:
        return True

    return False


def get_output_stats():
    """Get stats about the output file."""
    if not OUTPUT_FILE.exists():
        return "Output file not found"

    import pandas as pd
    try:
        df = pd.read_csv(OUTPUT_FILE)
        return f"{len(df):,} rows, {len(df.columns)} columns"
    except:
        size_mb = OUTPUT_FILE.stat().st_size / (1024 * 1024)
        return f"File size: {size_mb:.1f} MB"


def main():
    bot_token, chat_id = load_telegram_config()

    if not bot_token or not chat_id:
        print("ERROR: Telegram credentials not found!")
        return

    print("=" * 70)
    print("📬 Chunk 2020 Completion Notifier Started")
    print("=" * 70)
    print(f"Monitoring: {LOG_FILE.name}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Check interval: {CHECK_INTERVAL}s ({CHECK_INTERVAL/60:.0f} minutes)")
    print("\nWill send Telegram notification when chunk 2020 completes!")
    print("Running in background...\n")

    # Send startup notification
    startup_msg = (
        f"📬 Completion Notifier Started\n\n"
        f"Monitoring chunk 2020 fetch.\n"
        f"You'll get a notification when it completes!\n\n"
        f"Check interval: {CHECK_INTERVAL/60:.0f} minutes"
    )
    send_telegram(bot_token, chat_id, startup_msg)

    try:
        while True:
            if check_completion():
                # Fetch completed!
                progress = get_latest_progress()
                output_stats = get_output_stats()

                completion_msg = (
                    f"🎉 CHUNK 2020 FETCH COMPLETED!\n\n"
                    f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    f"Final progress:\n{progress['line'] if progress else 'N/A'}\n\n"
                    f"Output: {OUTPUT_FILE.name}\n"
                    f"Stats: {output_stats}\n\n"
                    f"✅ Ready to start chunk 2021!"
                )

                print(f"\n✅ Fetch completed! Sending notification...")
                if send_telegram(bot_token, chat_id, completion_msg):
                    print(f"✓ Notification sent successfully!")
                else:
                    print(f"✗ Failed to send notification")

                break

            # Still running - show status
            progress = get_latest_progress()
            if progress:
                status = f"[{progress['percent']:3d}%] Day {progress['current_day']}/{progress['total_days']}"
                print(f"\r{datetime.now().strftime('%H:%M:%S')} - {status} - Checking again in {CHECK_INTERVAL/60:.0f}m", end='')
            else:
                print(f"\r{datetime.now().strftime('%H:%M:%S')} - Waiting for data - Checking again in {CHECK_INTERVAL/60:.0f}m", end='')

            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("Completion notifier stopped by user")
        print("=" * 70)


if __name__ == "__main__":
    main()
