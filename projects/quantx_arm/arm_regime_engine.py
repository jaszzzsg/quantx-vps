#!/usr/bin/env python3
"""
ARM – Global Regime Engine (V2)
Clean version

Purpose:
- Run once per day (VPS cron later)
- Write ONE regime_state.json
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import os
from ib_vix import fetch_vix_from_ib
import sys
sys.path.append('/root/odte_strategy/scripts')
from telegram_notify import tg_send
import yfinance as yf

# =========================
# Paths
# =========================
BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
STATE_DIR = BASE_DIR / "state"

RULES_FILE = CONFIG_DIR / "regime_rules_v1.json"

# =========================
# Display Names (weather theme)
# =========================
REGIME_DISPLAY = {
    "R0":  ("CLEAR",    "☀️",  "Perfect bull — full sunshine, trade freely"),
    "R1":  ("SUNNY",    "🌤️",  "Strong bull — good conditions, trade normally"),
    "R1.5":("FAIR",     "🌥️",  "Mild bull — large caps leading, small caps lagging"),
    "R5":  ("HAZE",     "🌫️",  "Early recovery — green shoots, stay cautious"),
    "R2":  ("OVERCAST", "☁️",  "Oversold bounce — calm but no trend, watch for reversal"),
    "R4":  ("GUSTY",    "💨",  "Volatile trend — moving but bumpy, RF filter on"),
    "R3":  ("STORM",    "⛈️",  "Market breakdown — panic, Bull Put blocked"),
}
BLOCKS_FILE = CONFIG_DIR / "strategy_blocks.json"
STATE_FILE = STATE_DIR / "regime_state.json"

# =========================
# Helpers
# =========================
def read_json(path: Path) -> dict:
    with open(path, "r") as f:
        return json.load(f)


def read_prev_state() -> dict:
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def fetch_daily(symbol: str, days: int = 200) -> pd.DataFrame:
    df = yf.download(
        symbol,
        period=f"{days}d",
        interval="1d",
        progress=False,
        auto_adjust=True,
    )
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df

def to_float(x) -> float:
    # handles pandas scalar / 1-element Series safely (and avoids FutureWarning)
    try:
        # pandas Series / Index / numpy array-like
        if hasattr(x, "iloc"):
            return float(x.iloc[0])
        return float(x)
    except Exception:
        # last resort
        return float(x)

# =========================
# Core ARM logic
# =========================
def run_arm_v1():
    rules = read_json(RULES_FILE)
    blocks = read_json(BLOCKS_FILE)

    # ---- Fetch data ----
    spy = fetch_daily("SPY")
    iwm = fetch_daily("IWM")

    # ---- VIX (IBKR: fetches 1 month of daily bars for true 20-day MA) ----
    prev_state = read_prev_state()

    ib_host = os.getenv("IB_HOST", "127.0.0.1")
    ib_port = int(os.getenv("IB_PORT", "4002"))
    ib_client_id = int(os.getenv("IB_CLIENT_ID", "991"))
    vix_ma_period = rules.get("vix_ma_period", 20)

    vix_res = fetch_vix_from_ib(host=ib_host, port=ib_port, client_id=ib_client_id,
                                 ma_period=vix_ma_period)
    data_degraded = 0
    degraded_reason = ""

    if vix_res.ok and vix_res.vix is not None:
        vix_close = float(vix_res.vix)
        vix_ma = float(vix_res.vix_ma) if vix_res.vix_ma is not None else vix_close
        vix_asof = vix_res.asof
        vix_source = vix_res.source
    else:
        # Fallback to last saved values from state
        data_degraded = 1
        degraded_reason = f"VIX fetch failed: {vix_res.note}"
        vix_source = vix_res.source
        vix_close = float(prev_state.get("market", {}).get("vix_close", 0.0))
        vix_ma = float(prev_state.get("market", {}).get("vix_ma", 0.0))
        vix_asof = prev_state.get("market", {}).get("vix_asof")

    spy_close = to_float(spy["Close"].iloc[-1])
    iwm_close = to_float(iwm["Close"].iloc[-1])
    # ---- SPY trend score ----
    trend_score = 0
    for p in rules["ema_periods"]:
        ema = to_float(spy["Close"].ewm(span=p, adjust=False).mean().iloc[-1])
        if spy_close > ema:
            trend_score += 1

    # ---- IWM participation ----
    rs_iwm_spy = float(iwm_close / spy_close)
    # ---- VIX risk ----
    vix_risk_flag = int(vix_close > vix_ma)

    # ---- Regime mapping (V2) ----
    if trend_score == 3 and rs_iwm_spy >= 0.45 and vix_risk_flag == 0:
        regime = "R0"    # Perfect bull: strong trend + broad participation + calm VIX
    elif trend_score >= 2 and rs_iwm_spy >= 0.40 and vix_risk_flag == 0:
        regime = "R1"    # Strong bull: good trend + decent breadth + calm VIX
    elif trend_score >= 2 and vix_risk_flag == 0:
        regime = "R1.5"  # Moderate bull: trend but small caps lagging, calm VIX
    elif trend_score == 1 and vix_risk_flag == 0:
        regime = "R5"    # Early recovery: single EMA, calm VIX (tenuous green shoot)
    elif trend_score == 0 and vix_risk_flag == 0:
        regime = "R2"    # Oversold bounce: no trend but VIX calm (mean reversion)
    elif trend_score == 0 and vix_risk_flag == 1:
        regime = "R3"    # Risk-off: no trend + panic VIX (pure market breakdown)
    elif trend_score >= 1 and vix_risk_flag == 1:
        regime = "R4"    # Volatile trend: trending but elevated VIX
    else:
        regime = "R5"    # fallback (should not trigger)

    # ---- Flags (V2) ----
    flags = {
        "risk_off": int(regime in ["R3"]),
        "caution": int(regime in ["R2", "R4", "R5"]),
        "risk_on": int(regime in ["R0", "R1", "R1.5"]),
    }

    # ---- Apply blocklist for this regime ----
    regime_key = regime.replace(".", "_")  # "R1.5" -> "R1_5"
    blocked_today = blocks.get("global_blocks", {}).get(regime_key, [])

    # ---- State output ----
    _name, _emoji, _desc = REGIME_DISPLAY.get(regime, (regime, "❓", ""))
    state = {
        "asof_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "regime": regime,
        "regime_display": f"{_emoji} {_name}",
        "regime_desc": _desc,
        "scores": {
            "spy_trend_score": trend_score,   # 0–3
            "iwm_spy_rs": rs_iwm_spy,         # participation
            "vix_risk_flag": vix_risk_flag,   # 0/1
        },
        "market": {
            "vix_close": vix_close,
            "vix_ma": vix_ma,
            "vix_asof": vix_asof,
            "vix_source": vix_source
        },
        "data_degraded": int(data_degraded),
        "degraded_reason": degraded_reason,
        "flags": flags,
        "blocked_strategies_today": blocked_today,
        "strategy_blocklist": blocks.get("global_blocks", {}),
        "config": rules,
        "notes": "ARM V2 — fixed IWM thresholds (0.45/0.40), R5=early recovery, R4 caution, R1.5 risk_on, R3+R5 block BULL_PUT, VIX MA from IBKR 1-month rolling avg",
    }

    STATE_DIR.mkdir(exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    # ---- Telegram notify ----
    try:
        r = state.get('regime', '?')
        name, emoji, desc = REGIME_DISPLAY.get(r, (r, "❓", "Unknown"))
        flag_str = "RISK-OFF" if flags["risk_off"] else ("CAUTION" if flags["caution"] else "RISK-ON")
        vix_indicator = "⚠️" if vix_risk_flag else "✅"
        msg = (
            f"📊 ARM Regime | {state.get('asof_date')}\n"
            f"{emoji} {r} / {name} — {flag_str}\n"
            f"SPY trend: {trend_score}/3 | IWM/SPY: {rs_iwm_spy:.3f} | {vix_indicator} VIX: {vix_close:.1f} (MA: {vix_ma:.1f})\n"
            f"{desc}"
        )
        if state.get('data_degraded'):
            msg += f"\n⚠️ Data degraded: {state.get('degraded_reason')}"
        tg_send(msg)
    except Exception:
        pass

# =========================
# Entry point
# =========================
if __name__ == "__main__":
    run_arm_v1()
