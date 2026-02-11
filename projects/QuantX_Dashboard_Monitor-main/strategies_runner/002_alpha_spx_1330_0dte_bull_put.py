# =========================================================
# Alpha 002 — SPX 13:30 0DTE BULL PUT (Dashboard-native)
# ARM-only | Skip R3 | Retry window execution
# =========================================================

import os
import sys
import json
import csv
import math
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ib_insync import IB, Index, Option, Bag, ComboLeg, LimitOrder

BASE_PATH = "/root/projects/QuantX_Dashboard_Monitor-main"
sys.path.append(BASE_PATH)

from utils.client_id_manager import get_client_id
from utils.tg_notify import notify_enter, notify_skip

# =========================================================
# METADATA
# =========================================================
APP_NAME = "002_alpha_spx_1330_0dte_bull_put"
ALPHA_ID = "002"

# =========================================================
# IB CONFIG
# =========================================================
IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_ACCOUNT = "DUP148773"
CLIENT_ID = get_client_id(IB_HOST, IB_PORT, purpose="bull_put_1330", project="quantx_strategies")

# =========================================================
# PATHS
# =========================================================
LOG_DIR  = f"{BASE_PATH}/strategies_runner/logs/{APP_NAME}"
LOG_FILE = f"{LOG_DIR}/trade_log.csv"

ARM_JSON = "/root/projects/quantx_arm/state/regime_state.json"

STATE_DIR = "/root/odte_strategy/state"
BEAR_FLAG = f"{STATE_DIR}/bear_call_active_today.json"

# =========================================================
# PARAMETERS
# =========================================================
OTM_POINTS = 20
WIDTH      = 5
QTY        = 1
MIN_CREDIT = 1.00

# time window
ET = ZoneInfo("America/New_York")
ENTRY_START = (13, 30)
ENTRY_END   = (15, 10)
RETRY_SEC   = 60

# =========================================================
# TIME HELPERS
# =========================================================
def trade_date_et():
    return datetime.now(ET).strftime("%Y-%m-%d")

def utc_now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def now_et():
    return datetime.now(ET)

def in_window(t):
    h, m = t.hour, t.minute
    sh, sm = ENTRY_START
    eh, em = ENTRY_END
    return ((h > sh) or (h == sh and m >= sm)) and ((h < eh) or (h == eh and m <= em))

# =========================================================
# FILE / LOG
# =========================================================
def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

def log_event(action, regime=None, details=None):
    exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp_utc", "alpha_id", "action", "regime", "details"])
        w.writerow([utc_now_str(), ALPHA_ID, action, regime, json.dumps(details or {})])

# =========================================================
# ARM
# =========================================================
def load_arm_regime():
    if not os.path.isfile(ARM_JSON):
        return "NA"
    with open(ARM_JSON, "r") as f:
        return json.load(f).get("regime", "NA")

# =========================================================
# IB HELPERS
# =========================================================
def floor_to_5(x):
    return int(math.floor(x / 5) * 5)

def connect_ib():
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID, timeout=8)
    return ib

def _valid_px(v) -> bool:
    """True if v is a usable non-NaN price."""
    return v is not None and isinstance(v, (int, float)) and not math.isnan(v) and v > 0

def get_spx_price_and_contract(ib):
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(spx)
    # snapshot=True: one-shot pull from TWS cache — faster and cleaner for single-price checks
    t = ib.reqMktData(spx, "", snapshot=True, regulatorySnapshot=False)
    ib.sleep(3)
    px = next((v for v in (t.last, t.close, t.marketPrice()) if _valid_px(v)), None)
    ib.cancelMktData(spx)
    if px is None:
        raise RuntimeError(
            f"SPX price unavailable (snapshot) — last={t.last} close={t.close} "
            f"bid={t.bid} ask={t.ask} — check market data subscription"
        )
    return float(px), spx

def get_today_expiry_spxw(ib, spx):
    chains = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
    chain = next((c for c in chains if c.tradingClass == "SPXW"), None)
    if chain is None:
        raise RuntimeError("No SPXW chain")
    today = trade_date_et().replace("-", "")
    if today not in chain.expirations:
        raise RuntimeError("No 0DTE expiry")
    return today

def build_bull_put_spread(ib, expiry, spx_px):
    ref = floor_to_5(spx_px)
    short_k = ref - OTM_POINTS
    long_k  = short_k - WIDTH

    sell_put = Option("SPX", expiry, short_k, "P", "CBOE", tradingClass="SPXW")
    buy_put  = Option("SPX", expiry, long_k,  "P", "CBOE", tradingClass="SPXW")
    ib.qualifyContracts(sell_put, buy_put)

    spread = Bag(
        symbol="SPX",
        exchange="CBOE",
        currency="USD",
        comboLegs=[
            ComboLeg(conId=sell_put.conId, ratio=1, action="SELL", exchange="CBOE"),
            ComboLeg(conId=buy_put.conId,  ratio=1, action="BUY",  exchange="CBOE"),
        ],
    )
    return spread, short_k, long_k, ref

def get_mid_credit(ib, spread):
    # Spreads/combos require streaming (snapshot=True not supported for Bag)
    t = ib.reqMktData(spread, "", snapshot=False, regulatorySnapshot=False)
    ib.sleep(3)
    bid, ask = t.bid, t.ask   # capture before cancel
    ib.cancelMktData(spread)  # cancel each time — called in retry loop, must not stack subscriptions
    if not _valid_px(bid) or not _valid_px(ask):
        return None
    return round((bid + ask) / 2, 2)

def place_limit_sell(ib, spread, mid):
    order = LimitOrder("SELL", QTY, mid, account=IB_ACCOUNT)
    trade = ib.placeOrder(spread, order)
    ib.sleep(1)
    return trade.orderStatus.status or "UNKNOWN"

# =========================================================
# MAIN
# =========================================================
def main():
    ensure_dirs()

    td = trade_date_et()
    regime = load_arm_regime()

    # skip if Bear Call already active today
    if os.path.isfile(BEAR_FLAG):
        with open(BEAR_FLAG, "r") as f:
            if json.load(f).get("date") == td:
                notify_skip("BULL_PUT", "SPXW", "Bear Call active today", f"date={td}")
                log_event("SKIP_BEAR_ACTIVE", regime)
                return

    # ARM gate
    if regime == "R3":
        notify_skip("BULL_PUT", "SPXW", "ARM=R3 blocked", f"date={td}")
        log_event("SKIP_ARM_R3", regime)
        return

    if not in_window(now_et()):
        notify_skip("BULL_PUT", "SPXW", "Outside entry window", f"date={td}")
        log_event("SKIP_TIME", regime)
        return

    try:
        ib = connect_ib()
        spx_px, spx = get_spx_price_and_contract(ib)
        expiry = get_today_expiry_spxw(ib, spx)

        while True:
            if not in_window(now_et()):
                notify_skip("BULL_PUT", "SPXW", "Window expired (15:10 ET)", f"date={td}")
                log_event("SKIP_WINDOW_EXPIRED", regime)
                return

            spx_px, _ = get_spx_price_and_contract(ib)
            spread, short_k, long_k, ref = build_bull_put_spread(ib, expiry, spx_px)
            mid = get_mid_credit(ib, spread)

            if mid is None or mid < MIN_CREDIT:
                time.sleep(RETRY_SEC)
                continue

            status = place_limit_sell(ib, spread, mid)

            notify_enter(
                "BULL_PUT", "SPXW",
                expiry=expiry,
                short_strike=short_k,
                long_strike=long_k,
                credit=mid,
                extra=f"status={status} spx={spx_px:.2f} ref={ref} regime={regime}"
            )
            log_event("TRADE_ENTER", regime, {
                "expiry": expiry,
                "short_put": short_k,
                "long_put": long_k,
                "credit": mid,
                "status": status,
                "spx_px": spx_px,
                "ref": ref
            })
            return

    except Exception as e:
        notify_skip("BULL_PUT", "SPXW", "Exception", str(e))
        log_event("ERROR", regime, {"err": str(e)})
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()
