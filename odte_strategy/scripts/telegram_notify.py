import os
import json
import urllib.request

def _get_env(*keys):
    for k in keys:
        v = os.getenv(k)
        if v:
            return v
    return None

def tg_send(text: str):
    token = _get_env("TG_BOT_TOKEN", "TELEGRAM_BOT_TOKEN")
    chat_id = _get_env("TG_CHAT_ID", "TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "Missing TG_BOT_TOKEN/TG_CHAT_ID (or TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID)"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        body = r.read().decode("utf-8", errors="ignore")
    return True, body

if __name__ == "__main__":
    ok, info = tg_send("✅ Telegram notify test from VPS: arm/rf pipeline online.")
    print(ok, info[:200])
