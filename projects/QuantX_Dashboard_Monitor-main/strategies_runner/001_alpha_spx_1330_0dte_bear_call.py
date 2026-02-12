# =========================================================
# Alpha 001 — SPX 13:30 0DTE BEAR CALL (Dashboard-native)
# IB Gateway PAPER | Telegram ENTER/SKIP
#
# FOUNDATION RULES (LOCKED):
# - Decide ARM + RF once at 13:30 ET (gate)
# - Execution window: 13:30 -> 15:10 ET
# - Retry every 120s until MIN_CREDIT met; else SKIP at 15:10 ET
# - SPXW 0DTE uses 5-pt strikes
# =========================================================

import os
import sys
import json
import csv
import math
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
from ib_insync import IB, Index, Option, Bag, ComboLeg, LimitOrder

BASE_PATH = "/root/projects/QuantX_Dashboard_Monitor-main"
sys.path.append(BASE_PATH)

from utils.client_id_manager import get_client_id
from utils.tg_notify import notify_enter, notify_skip

APP_NAME = "001_alpha_spx_1330_0dte_bear_call"
ALPHA_ID = "001"

IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_ACCOUNT = "DUP148773"
CLIENT_ID = get_client_id(IB_HOST, IB_PORT, purpose="bear_call_1330", project="quantx_strategies")

LOG_DIR  = f"{BASE_PATH}/strategies_runner/logs/{APP_NAME}"
LOG_FILE = f"{LOG_DIR}/trade_log.csv"

ARM_JSON = "/root/projects/quantx_arm/state/regime_state.json"
RF_CSV   = "/root/odte_strategy/data/rf_daily_predictions.csv"

STATE_DIR = "/root/odte_strategy/state"
BEAR_FLAG = f"{STATE_DIR}/bear_call_active_today.json"

# ----- gates / parameters -----
# PAPER TRIAL: 2026-02-02 to 2026-02-06
# ORIGINAL: RF_THRESHOLD = 0.60 (60%)
# RESTORE TO 0.60 ON 2026-02-07!
RF_THRESHOLD = 0.10  # Lowered for paper trading trial

# ----- strategy params -----
OTM_POINTS   = 30
WIDTH        = 5
QTY          = 1
MIN_CREDIT   = 1.00

# ----- time window -----
ET = ZoneInfo("America/New_York")
ENTRY_START_HHMM = (13, 30)  # 1:30pm ET
ENTRY_END_HHMM   = (15, 10)  # 3:10pm ET
RETRY_SECONDS    = 60       # 1–2 min; set 60 if you want faster

def trade_date_et() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")

def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def now_et() -> datetime:
    return datetime.now(ET)

def in_entry_window(t: datetime) -> bool:
    h, m = t.hour, t.minute
    (sh, sm) = ENTRY_START_HHMM
    (eh, em) = ENTRY_END_HHMM
    start_ok = (h > sh) or (h == sh and m >= sm)
    end_ok   = (h < eh) or (h == eh and m <= em)
    return start_ok and end_ok

def ensure_dirs():
    os.makedirs(LOG_DIR, exist_ok=True)
    os.makedirs(STATE_DIR, exist_ok=True)

def log_event(action, regime=None, rf_prob=None, details=None):
    exists = os.path.isfile(LOG_FILE)
    with open(LOG_FILE, "a", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["timestamp_utc", "alpha_id", "action", "regime", "rf_prob", "details"])
        w.writerow([utc_now_str(), ALPHA_ID, action, regime, rf_prob, json.dumps(details or {})])

def load_arm_regime() -> str:
    if not os.path.isfile(ARM_JSON):
        return "NA"
    with open(ARM_JSON, "r") as f:
        j = json.load(f)
    return j.get("regime", "NA")

def load_rf_prob_for_date(trade_date: str):
    if not os.path.isfile(RF_CSV):
        return None
    df = pd.read_csv(RF_CSV)
    date_candidates = [c for c in df.columns if "date" in c.lower()]
    prob_candidates = [c for c in df.columns if "prob" in c.lower()]
    if not date_candidates or not prob_candidates:
        return None
    date_col = date_candidates[0]
    prob_col = prob_candidates[0]
    df[date_col] = pd.to_datetime(df[date_col].astype(str), format="%Y%m%d", errors="coerce").dt.strftime("%Y-%m-%d")
    row = df[df[date_col] == trade_date]
    if row.empty:
        return None
    try:
        return float(row.iloc[0][prob_col])
    except Exception:
        return None

def floor_to_5(x: float) -> int:
    return int(math.floor(x / 5) * 5)

def connect_ib() -> IB:
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=CLIENT_ID, timeout=8)
    return ib

def _valid_px(v) -> bool:
    """True if v is a usable non-NaN price."""
    return v is not None and isinstance(v, (int, float)) and not math.isnan(v) and v > 0

def get_spx_price_and_contract(ib: IB):
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

def get_today_expiry_spxw(ib: IB, spx: Index) -> str:
    chains = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
    chain = next((c for c in chains if getattr(c, "tradingClass", "") == "SPXW"), None) \
            or next((c for c in chains if getattr(c, "tradingClass", "") == "SPX"), None) \
            or (chains[0] if chains else None)
    if chain is None or not chain.expirations:
        raise RuntimeError("No option chains returned")
    today = trade_date_et().replace("-", "")
    if today not in chain.expirations:
        raise RuntimeError("No SPX options expiring today")
    return today

def build_bear_call_spread(ib: IB, expiry: str, spx_px: float):
    ref = floor_to_5(spx_px)
    short_k = ref + OTM_POINTS
    long_k  = short_k + WIDTH

    sell_call = Option("SPX", expiry, short_k, "C", "CBOE", tradingClass="SPXW")
    buy_call  = Option("SPX", expiry, long_k,  "C", "CBOE", tradingClass="SPXW")
    ib.qualifyContracts(sell_call, buy_call)

    spread = Bag(
        symbol="SPX",
        exchange="CBOE",
        currency="USD",
        comboLegs=[
            ComboLeg(conId=sell_call.conId, ratio=1, action="SELL", exchange="CBOE"),
            ComboLeg(conId=buy_call.conId,  ratio=1, action="BUY",  exchange="CBOE"),
        ],
    )

    return spread, short_k, long_k, ref, sell_call, buy_call

def get_mid_credit_from_legs(ib: IB, sell_leg: Option, buy_leg: Option):
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

def place_limit_sell_mid(ib: IB, spread: Bag, mid: float):
    order = LimitOrder("SELL", QTY, mid, account=IB_ACCOUNT)
    trade = ib.placeOrder(spread, order)
    ib.sleep(1)
    return trade.orderStatus.status or "UNKNOWN"

def main():
    ensure_dirs()

    td = trade_date_et()
    regime = load_arm_regime()

    # time guard
    tnow = now_et()
    if not in_entry_window(tnow):
        reason = f"Outside entry window (now={tnow.strftime('%H:%M')} ET)"
        notify_skip("BEAR_CALL", "SPXW", reason=reason, extra=f"date={td} regime={regime}")
        log_event("SKIP_TIME", regime=regime, rf_prob=None, details={"date": td, "now_et": tnow.isoformat()})
        return

    # Refresh RF score for today (idempotent)
    os.system("/root/odte_strategy/venv/bin/python /root/odte_strategy/scripts/rf_score_daily.py >/dev/null 2>&1")
    rf_prob = load_rf_prob_for_date(td)

    # RF gate decided once
    if rf_prob is None or rf_prob < RF_THRESHOLD:
        reason = f"RF<{RF_THRESHOLD} or missing"
        notify_skip("BEAR_CALL", "SPXW", reason=reason, extra=f"rf_prob={rf_prob} date={td} regime={regime}")
        log_event("SKIP_RF", regime=regime, rf_prob=rf_prob, details={"trade_date": td, "reason": reason})
        return

    # Execute with retry loop inside window
    try:
        ib = connect_ib()
    except Exception as e:
        notify_skip("BEAR_CALL", "SPXW", reason="IB connect failed", extra=str(e))
        log_event("SKIP_IB_DOWN", regime=regime, rf_prob=rf_prob, details={"err": str(e)})
        return

    try:
        spx_px, spx = get_spx_price_and_contract(ib)
        expiry = get_today_expiry_spxw(ib, spx)

        while True:
            tnow = now_et()
            if not in_entry_window(tnow):
                reason = "Window expired (15:10 ET)"
                notify_skip("BEAR_CALL", "SPXW", reason=reason, extra=f"date={td} regime={regime} rf={rf_prob}")
                log_event("SKIP_WINDOW_EXPIRED", regime=regime, rf_prob=rf_prob, details={"date": td})
                return

            # refresh SPX px for dynamic strikes each retry
            spx_px, _ = get_spx_price_and_contract(ib)
            spread, short_k, long_k, ref, sell_call, buy_call = build_bear_call_spread(ib, expiry, spx_px)
            mid = get_mid_credit_from_legs(ib, sell_call, buy_call)

            if mid is None:
                # no quote -> retry
                log_event("WAIT_NO_QUOTE", regime=regime, rf_prob=rf_prob, details={"mid": None, "now_et": tnow.strftime("%H:%M")})
                time.sleep(RETRY_SECONDS)
                continue

            if mid < MIN_CREDIT:
                # credit too low -> retry
                log_event("WAIT_CREDIT", regime=regime, rf_prob=rf_prob, details={"mid": mid, "min_credit": MIN_CREDIT, "now_et": tnow.strftime("%H:%M")})
                time.sleep(RETRY_SECONDS)
                continue

            status = place_limit_sell_mid(ib, spread, mid)

            # set bear flag for the day (so bull put skips)
            with open(BEAR_FLAG, "w") as f:
                json.dump({"date": td, "alpha": APP_NAME}, f)

            notify_enter(
                "BEAR_CALL", "SPXW",
                expiry=expiry,
                short_strike=short_k,
                long_strike=long_k,
                credit=mid,
                extra=f"status={status} spx={spx_px:.2f} ref={ref} rf={rf_prob:.3f} regime={regime}"
            )
            log_event("TRADE_ENTER", regime=regime, rf_prob=rf_prob, details={
                "expiry": expiry,
                "short_call": short_k,
                "long_call": long_k,
                "credit": mid,
                "status": status,
                "spx_px": spx_px,
                "ref": ref,
                "now_et": tnow.strftime("%H:%M"),
            })
            return

    except Exception as e:
        notify_skip("BEAR_CALL", "SPXW", reason="Exception", extra=str(e))
        log_event("ERROR", regime=regime, rf_prob=rf_prob, details={"err": str(e)})
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    main()
