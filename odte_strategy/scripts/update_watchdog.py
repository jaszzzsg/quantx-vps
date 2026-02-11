#!/usr/bin/env python3
import os
from datetime import datetime, timezone
import requests

# ===== CONFIG =====
ARM_STATE = "/root/projects/quantx_arm/state/regime_state.json"
RF_CSV = "/root/odte_strategy/data/rf_daily_predictions.csv"

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send(msg):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def file_updated_today(path):
    if not os.path.exists(path):
        return False
    mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    return mtime.date() == datetime.now(timezone.utc).date()

alerts = []

if not file_updated_today(ARM_STATE):
    alerts.append("❌ ARM regime NOT updated today")

if not file_updated_today(RF_CSV):
    alerts.append("❌ RF prediction NOT updated today")

if alerts:
    send("⚠️ ODTE WATCHDOG ALERT\n" + "\n".join(alerts))
