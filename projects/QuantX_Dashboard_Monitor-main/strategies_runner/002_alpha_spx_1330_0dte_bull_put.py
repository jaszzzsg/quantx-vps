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
    # Retry up to 3 times — snapshot=True can return NaN on a slow/flaky gateway
    for attempt in range(1, 4):
        t = ib.reqMktData(spx, "", snapshot=True, regulatorySnapshot=False)
        ib.sleep(3)
        px = next((v for v in (t.last, t.close, t.marketPrice()) if _valid_px(v)), None)
        ib.cancelMktData(spx)
        if px is not None:
            return float(px), spx
    raise RuntimeError(
        f"SPX price unavailable after 3 attempts (snapshot) — last={t.last} close={t.close} "
        f"bid={t.bid} ask={t.ask} — check market data subscription"
    )

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
    return spread, short_k, long_k, ref, sell_put, buy_put

def get_mid_credit_from_legs(ib, sell_leg, buy_leg):
    # Request snapshot for each leg individually — Bag/combo streaming unreliable for SPX spreads
    t_sell = ib.reqMktData(sell_leg, "", snapshot=True, regulatorySnapshot=False)
    t_buy  = ib.reqMktData(buy_leg,  "", snapshot=True, regulatorySnapshot=False)
    ib.sleep(4)
    ib.cancelMktData(sell_leg)
    ib.cancelMktData(buy_leg)
    if not all(_valid_px(v) for v in (t_sell.bid, t_sell.ask, t_buy.bid, t_buy.ask)):
        return None
    sell_mid = (t_sell.bid + t_sell.ask) / 2
    buy_mid  = (t_buy.bid  + t_buy.ask)  / 2
    mid = round(sell_mid - buy_mid, 2)
    return mid if mid > 0 else None

def has_open_spxw_position(ib, expiry) -> bool:
    """Return True if account already holds any SPXW legs for today's expiry."""
    for pos in ib.positions(IB_ACCOUNT):
        c = pos.contract
        if (c.symbol == "SPX"
                and getattr(c, "lastTradeDateOrContractMonth", "") == expiry
                and pos.position != 0):
            return True
    return False

def place_and_wait_fill(ib, spread, mid, timeout_sec=90):
    """Place DAY limit order and wait up to timeout_sec for a fill."""
    order = LimitOrder("SELL", QTY, mid, tif="DAY", account=IB_ACCOUNT)
    trade = ib.placeOrder(spread, order)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ib.sleep(2)
        status = trade.orderStatus.status
        if status in ("Filled", "Cancelled", "ApiCancelled", "Inactive"):
            break
    return trade.orderStatus.status or "UNKNOWN", int(trade.orderStatus.filled)

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

        # Position guard — skip if already holding SPXW legs for today
        if has_open_spxw_position(ib, expiry):
            notify_skip("BULL_PUT", "SPXW", "Already open position for today", f"expiry={expiry}")
            log_event("SKIP_ALREADY_OPEN", regime, {"expiry": expiry})
            return

        while True:
            if not in_window(now_et()):
                notify_skip("BULL_PUT", "SPXW", "Window expired (15:10 ET)", f"date={td}")
                log_event("SKIP_WINDOW_EXPIRED", regime)
                return

            spx_px, _ = get_spx_price_and_contract(ib)
            spread, short_k, long_k, ref, sell_put, buy_put = build_bull_put_spread(ib, expiry, spx_px)
            mid = get_mid_credit_from_legs(ib, sell_put, buy_put)

            if mid is None or mid < MIN_CREDIT:
                time.sleep(RETRY_SEC)
                continue

            status, filled = place_and_wait_fill(ib, spread, mid)

            notify_enter(
                "BULL_PUT", "SPXW",
                expiry=expiry,
                short_strike=short_k,
                long_strike=long_k,
                credit=mid,
                extra=f"status={status} filled={filled} spx={spx_px:.2f} ref={ref} regime={regime}"
            )
            log_event("TRADE_ENTER", regime, {
                "underlying": "SPX",
                "expiry": expiry,
                "short_put": short_k,
                "long_put": long_k,
                "credit": mid,
                "status": status,
                "filled": filled,
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
