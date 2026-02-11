#!/usr/bin/env python3
"""
run_strategy_window.py

ODTE single-shot runner:
- Wait until 13:30 New York time
- Read ARM regime JSON
- Read RF decision row for today's NY date (prob_safe + threshold + decision)
- Route:
    R0/R1/R1.5 -> BULL PUT
    R2/R3      -> BEAR CALL
    else       -> SKIP
- Base strikes on SPCFD anchor if available, else SPX snapshot
- Place ONE limit credit order:
    credit = max(1.00, mid)  (or 1.00 if no mid)
- NO CANCEL. If not filled, let it expire (DAY order).

Env (optional):
  IB_HOST=127.0.0.1
  IB_PORT=4002
  IB_CLIENT_ID=707
  DRY_RUN=0/1   (if 1, no order placed)

Paths:
  ARM JSON:   /root/projects/quantx_arm/state/regime_state.json
  RF CSV:     /root/odte_strategy/data/rf_daily_predictions.csv
  SPCFD JSON: /root/odte_strategy/state/spcfd.json
"""

import os
import sys
# ensure project root on PYTHONPATH
sys.path.insert(0, "/root/odte_strategy")

import json
import math
import time
import csv
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any


def notify_decision(decision: str, reason: str):
    """Send a single ODTE decision message at 13:30 NY."""
    try:
        msg = f"ODTE 13:30 NY — {decision}\nReason: {reason}"
        notify(msg)
    except Exception:
        pass

# Telegram notify helper
from utils.telegram_notify import notify


from ib_insync import IB, Index, Option, Contract, ComboLeg, LimitOrder

def env_trade_account() -> str:
    # Prefer explicit account vars; fallback to MODE-based.
    paper = os.getenv("IBKR_PAPER_ACCT", "").strip().strip('"')
    live  = os.getenv("IBKR_LIVE_ACCT", "").strip().strip('"')
    mode  = os.getenv("MODE", "").strip().upper()

    if mode == "PAPER" and paper:
        return paper
    if mode == "LIVE" and live:
        return live

    # If MODE not set, still allow forcing if only one is provided
    if paper and not live:
        return paper
    if live and not paper:
        return live

    return ""

NY = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")

ARM_JSON = "/root/projects/quantx_arm/state/regime_state.json"
RF_CSV = "/root/odte_strategy/data/rf_daily_predictions.csv"
SPCFD_JSON = "/root/odte_strategy/state/spcfd.json"

ENTRY_TIME_NY = (13, 30, 0)  # 1:30pm NY

MIN_CREDIT = 1.00
CONTRACT_QTY = 1

PUT_SHORT_OFFSET = 20
CALL_SHORT_OFFSET = 20
SPREAD_WIDTH = 5

BULL_PUT_REGIMES = {"R0", "R1", "R1.5", "R4", "R5"}
BEAR_CALL_REGIMES = {"R2", "R3"}


def log(msg: str) -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{ts}] {msg}", flush=True)


def die(msg: str, code: int = 1) -> None:
    log(f"ERROR: {msg}")
    sys.exit(code)


def ny_now() -> datetime:
    return datetime.now(NY)


def today_ny_str() -> str:
    return ny_now().strftime("%Y-%m-%d")


def sleep_until_ny(h: int, m: int, s: int) -> None:
    now = ny_now()
    target = now.replace(hour=h, minute=m, second=s, microsecond=0)
    if now >= target:
        log(f"Target time already passed: {target.isoformat()} NY. Continuing now.")
        return
    delta = (target - now).total_seconds()
    log(f"Sleeping until {target.isoformat()} NY (in {int(delta)}s).")
    time.sleep(max(0, delta))


def floor_to_5(x: float) -> int:
    return int(math.floor(x / 5.0) * 5)


def ceil_to_5(x: float) -> int:
    return int(math.ceil(x / 5.0) * 5)


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def try_read_spcfd_anchor(path: str) -> Optional[float]:
    if not os.path.exists(path):
        return None
    try:
        data = load_json(path)
    except Exception as e:
        log(f"SPCFD read failed ({path}): {e}")
        return None

    candidates = [
        "spcfd", "value", "anchor", "price", "close", "last", "mid",
        "SPCFD", "Value", "Anchor", "Price", "Close", "Last", "Mid",
    ]

    def find_number(obj: Any) -> Optional[float]:
        if isinstance(obj, (int, float)) and math.isfinite(float(obj)):
            return float(obj)
        if isinstance(obj, str):
            try:
                v = float(obj.strip())
                if math.isfinite(v):
                    return v
            except Exception:
                return None
        if isinstance(obj, dict):
            for k in candidates:
                if k in obj:
                    v = find_number(obj[k])
                    if v is not None:
                        return v
            for v0 in obj.values():
                v = find_number(v0)
                if v is not None:
                    return v
        if isinstance(obj, list):
            for it in obj:
                v = find_number(it)
                if v is not None:
                    return v
        return None

    return find_number(data)


def parse_arm_regime(arm: Dict[str, Any]) -> str:
    regime = arm.get("regime") or arm.get("arm_regime")
    if not regime or not isinstance(regime, str):
        die(f"ARM JSON missing/invalid 'regime': {arm}")
    return regime.strip()


def read_rf_row_for_date(rf_csv_path: str, date_yyyy_mm_dd: str) -> Optional[Dict[str, Any]]:
    if not os.path.exists(rf_csv_path):
        return None
    try:
        with open(rf_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (row.get("date") or "").strip() == date_yyyy_mm_dd:
                    # normalize types
                    out = dict(row)
                    for k in ["prob_safe", "threshold", "regime_num"]:
                        if k in out and out[k] not in (None, ""):
                            try:
                                out[k] = float(out[k])
                            except Exception:
                                pass
                    return out
        return None
    except Exception as e:
        log(f"RF CSV read failed ({rf_csv_path}): {e}")
        return None


@dataclass
class Decision:
    action: str  # "BULL_PUT" / "BEAR_CALL" / "SKIP"
    regime: str
    prob_safe: float
    threshold: float
    why: str


def decide_from_rf(regime: str, rf_row: Dict[str, Any], force_trade: bool = False) -> Decision:
    prob_safe = float(rf_row.get("prob_safe"))
    thr = float(rf_row.get("threshold"))
    rf_decision = (rf_row.get("decision") or "").strip().upper()

    if force_trade:
        rf_decision = "TRADE"


    # route by regime first
    if regime in BULL_PUT_REGIMES:
        action = "BULL_PUT"
    elif regime in BEAR_CALL_REGIMES:
        action = "BEAR_CALL"
    else:
        return Decision("SKIP", regime, prob_safe, thr, "Regime not routed")

    # gate by RF decision (already uses plan thresholds)
    if rf_decision != "TRADE":
        return Decision("SKIP", regime, prob_safe, thr, f"RF decision={rf_decision or 'UNKNOWN'}")

    return Decision(action, regime, prob_safe, thr, "RF TRADE + regime route")


def ib_connect() -> IB:
    host = os.getenv("IB_HOST", "127.0.0.1")
    port = int(os.getenv("IB_PORT", "4002"))
    cid = int(os.getenv("IB_CLIENT_ID", "707"))

    ib = IB()
    log(f"Connecting IB: {host}:{port} clientId={cid} ...")
    ib.connect(host, port, clientId=cid, timeout=10)
    if not ib.isConnected():
        die("IB connect failed.")
    log("IB connected.")
    return ib


def pick_spxw_expiry_today(ib: IB, spx: Index) -> str:
    ib.qualifyContracts(spx)
    chains = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)
    if not chains:
        die("No option chains returned for SPX.")

    chain = next((c for c in chains if getattr(c, "tradingClass", "") == "SPXW"), None) \
            or next((c for c in chains if getattr(c, "tradingClass", "") == "SPX"), None) \
            or chains[0]

    today = today_ny_str().replace("-", "")
    expirations = sorted(set(chain.expirations))
    if not expirations:
        die("No expirations in option chain.")

    if today in expirations:
        return today
    for e in expirations:
        if e > today:
            return e
    return expirations[-1]


def snapshot_spx_price(ib: IB, spx: Index) -> Optional[float]:
    try:
        t = ib.reqMktData(spx, "", snapshot=True, regulatorySnapshot=False)
        ib.sleep(1.5)
        for v in [t.last, t.marketPrice(), t.close]:
            if v is not None and isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) > 0:
                return float(v)
    except Exception as e:
        log(f"SPX snapshot failed: {e}")
    return None


def build_credit_spread_bag(
    ib: IB,
    expiry: str,
    right: str,              # "P" or "C"
    short_strike: float,
    long_strike: float,
) -> Contract:
    short_opt = Option("SPX", expiry, float(short_strike), right, "CBOE", tradingClass="SPXW")
    long_opt  = Option("SPX", expiry, float(long_strike),  right, "CBOE", tradingClass="SPXW")
    ib.qualifyContracts(short_opt, long_opt)

    bag = Contract()
    bag.secType = "BAG"
    bag.symbol = "SPX"
    bag.currency = "USD"
    bag.exchange = "SMART"
    bag.comboLegs = []

    leg1 = ComboLeg()
    leg1.conId = short_opt.conId
    leg1.ratio = 1
    leg1.action = "SELL"
    leg1.exchange = "CBOE"

    leg2 = ComboLeg()
    leg2.conId = long_opt.conId
    leg2.ratio = 1
    leg2.action = "BUY"
    leg2.exchange = "CBOE"

    bag.comboLegs = [leg1, leg2]
    return bag


def compute_mid_credit(ib: IB, bag: Contract) -> Optional[float]:
    try:
        t = ib.reqMktData(bag, "", snapshot=True, regulatorySnapshot=False)
        ib.sleep(1.8)
        bid = getattr(t, "bid", None)
        ask = getattr(t, "ask", None)
        if bid is not None and ask is not None and bid > 0 and ask > 0 and ask >= bid:
            return float((bid + ask) / 2.0)
        mp = t.marketPrice()
        if mp is not None and isinstance(mp, (int, float)) and mp > 0:
            return float(mp)
    except Exception as e:
        log(f"Mid credit snapshot failed: {e}")
    return None


def main() -> int:
    dry_run = os.getenv("DRY_RUN", "0").strip() == "1"
    force_trade = os.getenv("FORCE_TRADE", "0").strip() == "1"
    force_trade = os.getenv("FORCE_TRADE", "0").strip() == "1"

    sleep_until_ny(*ENTRY_TIME_NY)

    if not os.path.exists(ARM_JSON):
        die(f"ARM JSON not found: {ARM_JSON}")
    arm = load_json(ARM_JSON)
    regime = parse_arm_regime(arm)
    log(f"ARM regime={regime}")

    d = today_ny_str().replace("-", "")
    rf_row = read_rf_row_for_date(RF_CSV, d)
    if rf_row is None:
        notify_decision("SKIP", f"RF row missing for {d} (YYYYMMDD)")

        die(f"RF row missing for {d} (YYYYMMDD) in {RF_CSV} (run rf_score_daily.py first)")

    log(f"RF row for {d}: prob_safe={rf_row.get('prob_safe')} thr={rf_row.get('threshold')} decision={rf_row.get('decision')}")

    dec = decide_from_rf(regime, rf_row, force_trade)
    log(f"Decision: {dec.action} (why={dec.why}) thr={dec.threshold:.2f} prob_safe={dec.prob_safe:.4f}")

    if dec.action == "SKIP":
        log("SKIP ✅ Exiting.")
        notify_decision("SKIP", dec.why)
        return

    anchor = try_read_spcfd_anchor(SPCFD_JSON)
    if anchor is not None and anchor > 0:
        log(f"Using SPCFD anchor for strikes: {anchor}")
    else:
        log("SPCFD anchor not found/readable. Will use SPX snapshot for strikes.")

    ib = ib_connect()
    try:
        spx = Index("SPX", "CBOE", "USD")
        ib.qualifyContracts(spx)

        base_px = float(anchor) if (anchor is not None and anchor > 0) else snapshot_spx_price(ib, spx)
        if base_px is None or not math.isfinite(base_px) or base_px <= 0:
            die("Could not obtain a valid base price (anchor missing and SPX snapshot failed).")
        log(f"Base price used: {base_px}")

        expiry = pick_spxw_expiry_today(ib, spx)
        log(f"Using expiry: {expiry} (SPXW preferred)")

        if dec.action == "BULL_PUT":
            short_strike = floor_to_5(base_px) - PUT_SHORT_OFFSET
            long_strike = short_strike - SPREAD_WIDTH
            right = "P"
            log(f"Build BULL PUT: shortP={short_strike} longP={long_strike}")
        else:
            short_strike = ceil_to_5(base_px) + CALL_SHORT_OFFSET
            long_strike = short_strike + SPREAD_WIDTH
            right = "C"
            log(f"Build BEAR CALL: shortC={short_strike} longC={long_strike}")

        bag = build_credit_spread_bag(ib, expiry, right, short_strike, long_strike)

        mid = compute_mid_credit(ib, bag)
        if mid is None or not math.isfinite(mid) or mid <= 0:
            credit = MIN_CREDIT
            log(f"Mid not available -> credit set to MIN_CREDIT={credit:.2f}")
        else:
            credit = max(MIN_CREDIT, float(mid))
            log(f"Mid={mid:.2f} -> credit={credit:.2f} (min {MIN_CREDIT:.2f})")

        # DAY order (default). NO CANCEL. Let it expire if not filled.
        order = LimitOrder("SELL", CONTRACT_QTY, round(credit, 2))

        acct = env_trade_account()
        if acct:
            order.account = acct
            log(f"Force order.account={acct}")
        log(f"Placing ONE order: SELL {CONTRACT_QTY}x BAG @ {order.lmtPrice:.2f}  dry_run={dry_run}")
        if dry_run:
            log("DRY_RUN=1 so no order placed. Exiting.")
            notify_decision("DRY_RUN", f"{route} @ credit {order.lmtPrice:.2f}")
            return
        trade = ib.placeOrder(bag, order)
        log(f"Submitted. status={trade.orderStatus.status} (no cancel; will expire if not filled)")
        notify_decision("ORDER_SENT", f"{route} @ credit {order.lmtPrice:.2f}")

        log(f"Submitted. status={trade.orderStatus.status} (no cancel; will expire if not filled)")
        log("Done. Exiting.")
        return 0

    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
                log("IB disconnected.")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
