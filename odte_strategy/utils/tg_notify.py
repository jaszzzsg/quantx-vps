import os
import requests
from datetime import datetime, timezone

def _get_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing env var: {name}")
    return v

def tg_send(text: str) -> bool:
    """
    Sends a plain text Telegram message.
    Requires env vars:
      TG_BOT_TOKEN, TG_CHAT_ID
    """
    token = _get_env("TG_BOT_TOKEN")
    chat_id = _get_env("TG_CHAT_ID")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=10)
    return r.status_code == 200

def _ts_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def notify_enter(strategy: str, symbol: str, expiry: str, short_strike: float, long_strike: float,
                 credit: float | None = None, extra: str | None = None) -> None:
    msg = (
        f"✅ ENTER\n"
        f"{symbol} {strategy}\n"
        f"Expiry: {expiry}\n"
        f"Short/Long: {short_strike}/{long_strike}\n"
    )
    if credit is not None:
        msg += f"Credit: {credit}\n"
    if extra:
        msg += f"{extra}\n"
    msg += f"Time: {_ts_utc()}"
    tg_send(msg)

def notify_skip(strategy: str, symbol: str, reason: str, extra: str | None = None) -> None:
    msg = (
        f"⏭️ SKIP\n"
        f"{symbol} {strategy}\n"
        f"Reason: {reason}\n"
    )
    if extra:
        msg += f"{extra}\n"
    msg += f"Time: {_ts_utc()}"
    tg_send(msg)

def notify_exit(strategy: str, symbol: str, reason: str, pnl: float | None = None,
                extra: str | None = None) -> None:
    msg = (
        f"🏁 EXIT\n"
        f"{symbol} {strategy}\n"
        f"Reason: {reason}\n"
    )
    if pnl is not None:
        msg += f"PnL: {pnl}\n"
    if extra:
        msg += f"{extra}\n"
    msg += f"Time: {_ts_utc()}"
    tg_send(msg)
