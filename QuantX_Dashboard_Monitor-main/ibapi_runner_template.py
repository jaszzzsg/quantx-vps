"""
IBAPI Strategy Runner Template (Production-Ready)

Key Features:
- Pure IBAPI (EClient/EWrapper) – no ib_insync
- Auto-manages client IDs via client_id_manager
- Logs ONLY IB-confirmed fills (no pre-submit logs)
- Trade log written as:
      strategies_runner/logs/<APP_NAME>/trade_log.csv
- Dashboard-compatible CSV schema:
    timestamp, symbol, action, price, quantity, pnl, duration,
    position, status, ib_order_id, extra
- Thread-safe logging, deduping, sorted by timestamp
- Prevents duplicate trades
- Prevents looping BUY→BUY or SELL→SELL
- Enforces:
      • MIN_QTY = 1
      • MAX_CAPITAL_PER_TRADE_USD = 2000
      • cool-down between orders
"""

import os
import sys
import time
import json
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any

import pandas as pd
import numpy as np
import datetime as dt

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.common import TickerId

# ---------------------------------------------------------------
# Inject root path for client_id_manager
# ---------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from utils.client_id_manager import get_or_allocate_client_id, bump_client_id


# ===================================================================
# CONFIG — SET THESE FOR EACH STRATEGY
# ===================================================================
APP_NAME = "MY_STRATEGY_IBAPI"      # e.g.: "ME_RANK1", "IYW_GLD_volguard"

HOST = "127.0.0.1"
PORT = 7497                         # TWS: 7497 paper / 7496 live
ACCOUNT_ID = None                   # "U1234567" or None

SYMBOL = "AAPL"
SEC_TYPE = "STK"
EXCHANGE = "SMART"
CURRENCY = "USD"

MAX_CAPITAL_PER_TRADE_USD = 2000
MIN_QTY = 1

COOLDOWN_SEC = 60
MIN_PRICE_MOVE = 0.003   # for same-side actions, min 0.3% change

# Logging paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_ROOT = os.path.join(BASE_DIR, "logs", APP_NAME)
os.makedirs(LOG_ROOT, exist_ok=True)

TRADE_LOG_PATH = os.path.join(LOG_ROOT, "trade_log.csv")
STATUS_LOG_PATH = os.path.join(LOG_ROOT, "status.log")
HEARTBEAT_PATH = os.path.join(LOG_ROOT, "heartbeat.json")

CLIENT_ID = get_or_allocate_client_id(name=APP_NAME, role="strategy")


# ===================================================================
# TRADE LOG STRUCTURE
# ===================================================================
@dataclass
class TradeRow:
    timestamp: dt.datetime
    symbol: str
    action: str
    price: float
    quantity: int
    pnl: float
    duration: float
    position: str
    status: str
    ib_order_id: int
    extra: Dict[str, Any] = field(default_factory=dict)


# ===================================================================
# LOGGER
# ===================================================================
def log_status(msg: str):
    ts = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}][{APP_NAME}] {msg}"
    print(line)
    try:
        with open(STATUS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except:
        pass


# ===================================================================
# STRATEGY RUNNER (IBAPI)
# ===================================================================
class IBKRStrategy(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

        # State
        self.current_position = "NONE"
        self.current_qty = 0
        self.entry_price: Optional[float] = None
        self.entry_time: Optional[dt.datetime] = None

        # Cooldown
        self.last_trade_time = None
        self.last_action = None
        self.last_action_price = None

        # Buffers
        self.buff: List[TradeRow] = []
        self.lock = threading.Lock()

        # Market data
        self.latest_price = None

        # Order tracking
        self._logged_order_ids = {}

        # Contract
        self.contract = self._build_contract()

        # Stop flag
        self.stop_flag = False

    # -----------------------------------------------------------------
    # CONTRACT
    # -----------------------------------------------------------------
    def _build_contract(self) -> Contract:
        c = Contract()
        c.symbol = SYMBOL
        c.secType = SEC_TYPE
        c.exchange = EXCHANGE
        c.currency = CURRENCY
        return c

    # -----------------------------------------------------------------
    # FILE IO
    # -----------------------------------------------------------------
    def flush_log(self):
        with self.lock:
            if not self.buff:
                return

            new_rows = [{
                "timestamp": r.timestamp.isoformat(),
                "symbol": r.symbol,
                "action": r.action,
                "price": r.price,
                "quantity": r.quantity,
                "pnl": r.pnl,
                "duration": r.duration,
                "position": r.position,
                "status": r.status,
                "ib_order_id": r.ib_order_id,
                "extra": json.dumps(r.extra) if r.extra else None,
            } for r in self.buff]

            df_new = pd.DataFrame(new_rows)
            self.buff.clear()

        if os.path.exists(TRADE_LOG_PATH):
            try:
                df_old = pd.read_csv(TRADE_LOG_PATH)
            except:
                df_old = pd.DataFrame()
            df = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df = df_new

        # Cleanup
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        df["dedup_key"] = (
            df["timestamp"].astype(str)
            + "|" + df["symbol"].astype(str)
            + "|" + df["action"].astype(str)
            + "|" + df["ib_order_id"].astype(str)
        )
        df = df.drop_duplicates(subset=["dedup_key"]).drop(columns=["dedup_key"])

        df = df.sort_values("timestamp")
        df.to_csv(TRADE_LOG_PATH, index=False)

    # -----------------------------------------------------------------
    # HEARTBEAT
    # -----------------------------------------------------------------
    def write_heartbeat(self, status="running"):
        data = {
            "app_name": APP_NAME,
            "symbol": SYMBOL,
            "status": status,
            "last_update": dt.datetime.utcnow().isoformat(),
            "position": self.current_position,
            "position_qty": self.current_qty,
            "last_price": self.latest_price,
        }
        try:
            with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except:
            pass

    # -----------------------------------------------------------------
    # MARKET DATA
    # -----------------------------------------------------------------
    def tickPrice(self, reqId: TickerId, tickType, price, attrib):
        if price > 0:
            self.latest_price = float(price)
            self.evaluate_signal()

    # -----------------------------------------------------------------
    # STRATEGY LOGIC (YOU EDIT THIS)
    # -----------------------------------------------------------------
    def compute_signal(self, price: float) -> Optional[str]:
        """
        Override per-strategy.
        Must return: "BUY", "SELL", or None
        """
        return None  # placeholder

    # -----------------------------------------------------------------
    # CHECKS & SIZING
    # -----------------------------------------------------------------
    def can_trade(self, action: str, price: float):
        now = dt.datetime.utcnow()

        # Cooldown
        if self.last_trade_time:
            if (now - self.last_trade_time).total_seconds() < COOLDOWN_SEC:
                return False

        # Repeat same action check
        if self.last_action == action and self.last_action_price:
            if abs(price - self.last_action_price) / self.last_action_price < MIN_PRICE_MOVE:
                return False

        # Position gating
        if action == "BUY" and self.current_position == "LONG":
            return False
        if action == "SELL" and self.current_position == "NONE":
            return False

        return True

    def qty_for_price(self, price: float) -> int:
        if price <= 0:
            return 0
        max_qty = int(MAX_CAPITAL_PER_TRADE_USD // price)
        if max_qty < MIN_QTY:
            return 0
        return max_qty

    # -----------------------------------------------------------------
    # EXECUTION
    # -----------------------------------------------------------------
    def evaluate_signal(self):
        if self.latest_price is None:
            return

        price = self.latest_price
        action = self.compute_signal(price)

        if action not in ("BUY", "SELL"):
            self.write_heartbeat("running")
            return

        if not self.can_trade(action, price):
            self.write_heartbeat("running")
            return

        qty = self.qty_for_price(price)
        if qty <= 0:
            return

        self.place_market_order(action, qty, price)

    def place_market_order(self, action: str, qty: int, price: float):
        order = Order()
        order.action = action
        order.orderType = "MKT"
        order.totalQuantity = qty
        if ACCOUNT_ID:
            order.account = ACCOUNT_ID

        oid = self.nextOrderId
        self.placeOrder(oid, self.contract, order)
        log_status(f"Placed {action} {qty} @ ~{price:.4f}, oid={oid}")

        self.last_trade_time = dt.datetime.utcnow()
        self.last_action = action
        self.last_action_price = price

    # -----------------------------------------------------------------
    # FILL EVENTS (CONFIRMED BY IBKR)
    # -----------------------------------------------------------------
    def execDetails(self, reqId, contract, execution):
        oid = execution.orderId
        if oid in self._logged_order_ids:
            return

        action = execution.side.upper()
        qty = execution.shares
        price = execution.price
        now = dt.datetime.utcnow().replace(tzinfo=None)

        pnl = 0.0
        duration = 0.0
        pos_after = self.current_position

        # BUY → enter long
        if action == "BUY":
            self.current_position = "LONG"
            self.current_qty = qty
            self.entry_price = price
            self.entry_time = now
            pos_after = "LONG"

        # SELL → close long
        elif action == "SELL":
            if self.current_position == "LONG" and self.entry_price:
                pnl = (price - self.entry_price) * qty

            if self.entry_time:
                duration = (now - self.entry_time).total_seconds()

            self.current_position = "NONE"
            self.current_qty = 0
            self.entry_price = None
            self.entry_time = None
            pos_after = "NONE"

        row = TradeRow(
            timestamp=now,
            symbol=SYMBOL,
            action=action,
            price=price,
            quantity=qty,
            pnl=pnl,
            duration=duration,
            position=pos_after,
            status="Filled",
            ib_order_id=oid,
            extra={
                "execID": execution.execId,
                "permID": execution.permId,
                "clientID": execution.clientId,
            },
        )

        with self.lock:
            self.buff.append(row)
        self.flush_log()

        self._logged_order_ids[oid] = True
        log_status(f"FILL: {action} x{qty} @ {price}, pnl={pnl:.2f}")

    # -----------------------------------------------------------------
    def error(self, reqId, errorCode, errorString):
        log_status(f"Error {errorCode}: {errorString}")

        if errorCode == 501:  # client ID in use
            new_id = bump_client_id(name=APP_NAME, role="strategy")
            log_status(f"Client ID in use → bumping to {new_id}")
            self.disconnect()
            time.sleep(1)
            self.connect(HOST, PORT, new_id)
            self.nextOrderId = 1

    # -----------------------------------------------------------------
    def nextValidId(self, orderId):
        self.nextOrderId = orderId

        # Begin market data
        log_status("Requesting market data…")
        self.reqMktData(1, self.contract, "", False, False, [])

    # -----------------------------------------------------------------
    def run_loop(self):
        while not self.stop_flag and self.isConnected():
            self.run()


# ===================================================================
# MAIN ENTRY
# ===================================================================
def main():
    ib = IBKRStrategy()
    log_status(f"Connecting to IBKR {HOST}:{PORT} (clientId={CLIENT_ID})")
    ib.connect(HOST, PORT, CLIENT_ID)

    thread = threading.Thread(target=ib.run_loop, daemon=True)
    thread.start()

    try:
        while True:
            time.sleep(1)
            ib.write_heartbeat("running")
    except KeyboardInterrupt:
        log_status("Shutting down…")
        ib.stop_flag = True
        ib.disconnect()


if __name__ == "__main__":
    main()
