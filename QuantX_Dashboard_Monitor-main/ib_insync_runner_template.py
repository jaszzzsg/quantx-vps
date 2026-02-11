"""
IBKR-Confirmed Strategy Runner Template (ib_insync, production-ready)

Usage:
- Copy this file as e.g. `spy_ema50_runner.py`, `volguard_runner.py`, etc.
- Set APP_NAME, SYMBOL, etc. in the CONFIG section.
- Implement `compute_signal(self, price: float) -> str | None` with your logic.

Key Features:
- Connects to IBKR (TWS or Gateway) with a unique client ID from client_id_manager.
- Subscribes to live market data via ib_insync.
- Places orders with:
    • MIN_QTY = 1
    • MAX_CAPITAL_PER_TRADE_USD = 2000 (enforced)
- Logs ONLY IB-confirmed fills:
    • No log row is written until IBKR reports a Filled/PartiallyFilled status.
- Logs to:
    strategies_runner/logs/<APP_NAME>/trade_log.csv
- Trade log columns match the read-only dashboard expectation:
    timestamp, symbol, action, price, quantity, pnl, duration,
    position, status, ib_order_id, plus an "extra" JSON column.
"""

import os
import sys
import json
import time
import threading
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

import pandas as pd
import numpy as np
import datetime as dt

from ib_insync import (
    IB,
    Stock,
    Forex,
    Index,
    Future,
    Option,
    Contract as IBContract,
    MarketOrder,
    Trade,
)

# ─────────────────────────────────────────────────────────────
# PATH & CLIENT ID MANAGER WIRES
# ─────────────────────────────────────────────────────────────
# Assume project root is one level above this file:
#   project_root/
#     dashboard_read_only.py
#     utils/client_id_manager.py
#     strategies_runner/this_file.py

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from utils.client_id_manager import get_or_allocate_client_id, bump_client_id  # type: ignore


# ─────────────────────────────────────────────────────────────
# CONFIG — EDIT THESE FOR EACH STRATEGY
# ─────────────────────────────────────────────────────────────
APP_NAME = "MY_STRATEGY_NAME"  # e.g. "ME_RANK1", "IYW_GLD_volguard"

HOST = "127.0.0.1"
PORT = 7497                 # 7497 paper, 7496 live, or your Gateway port
ACCOUNT_ID = None           # e.g. "UXXXXXXX" or None

SYMBOL = "AAPL"
SEC_TYPE = "STK"            # STK | IND | FX | FUT | OPT
EXCHANGE = "SMART"
CURRENCY = "USD"

MAX_CAPITAL_PER_TRADE_USD = 2000.0
MIN_QTY = 1                 # min 1 share/contract per trade

COOLDOWN_SEC = 60           # min seconds between new trades
MIN_SAME_ACTION_REPRICE = 0.003  # 0.3% price move before repeating same side

USE_RTH = False             # for historical data (if used)
HIST_DURATION = "30 D"
HIST_BAR_SIZE = "1 hour"
HIST_WHAT = "TRADES"

# Logs:
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # strategies_runner/
LOG_ROOT = os.path.join(BASE_DIR, "logs", APP_NAME)
os.makedirs(LOG_ROOT, exist_ok=True)

TRADE_LOG_PATH = os.path.join(LOG_ROOT, "trade_log.csv")
HEARTBEAT_PATH = os.path.join(LOG_ROOT, "heartbeat.json")
STATUS_LOG_PATH = os.path.join(LOG_ROOT, "status.log")

# Allocate a stable client ID for this strategy
CLIENT_ID = get_or_allocate_client_id(name=APP_NAME, role="strategy", preferred=None)


# ─────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────
# HELPER LOGGER
# ─────────────────────────────────────────────────────────────
def log_status(msg: str) -> None:
    ts = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}][{APP_NAME}] {msg}"
    print(line)
    try:
        with open(STATUS_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# STRATEGY RUNNER
# ─────────────────────────────────────────────────────────────
class StrategyRunner:
    def __init__(self) -> None:
        self.ib = IB()
        self.contract = self._build_contract()

        # Position state (simple: long or flat; extend if you need shorts)
        self.current_position: str = "NONE"  # NONE | LONG
        self.current_qty: int = 0
        self.entry_price: Optional[float] = None
        self.entry_time: Optional[dt.datetime] = None

        # Trade throttling
        self.last_trade_time: Optional[dt.datetime] = None
        self.last_action: Optional[str] = None
        self.last_action_price: Optional[float] = None

        # In-memory rows waiting to be flushed
        self.trade_log_buffer: List[TradeRow] = []
        self.lock = threading.Lock()

        # Market data ticker
        self._ticker = None

        # Stopping flag
        self._stop_requested = False

        # Keep track of which orders we've already logged fills for
        self._logged_order_ids: Dict[int, bool] = {}

        # Simple price history if you need indicators
        self.prices: List[float] = []

    # ─────────────────────────────
    # CONTRACT BUILDING
    # ─────────────────────────────
    def _build_contract(self):
        stype = SEC_TYPE.upper()
        if stype == "STK":
            return Stock(SYMBOL, EXCHANGE, CURRENCY)
        if stype == "IND":
            return Index(SYMBOL, EXCHANGE, CURRENCY)
        if stype == "FX":
            return Forex(SYMBOL)
        if stype == "FUT":
            return Future(SYMBOL, exchange=EXCHANGE, currency=CURRENCY)
        if stype == "OPT":
            # Template; you should specify expiry/strike for real use
            return Option(SYMBOL, "", 0.0, "C", EXCHANGE, currency=CURRENCY)
        # Fallback generic contract
        return IBContract(conId=0, symbol=SYMBOL, secType=SEC_TYPE, exchange=EXCHANGE, currency=CURRENCY)

    # ─────────────────────────────
    # FILE IO
    # ─────────────────────────────
    def _flush_trade_log_buffer(self) -> None:
        """
        Append new rows to CSV; deduplicate by (timestamp, symbol, action, ib_order_id).
        Ensures the file is sorted by timestamp ascending.
        """
        with self.lock:
            if not self.trade_log_buffer:
                return

            rows = []
            for r in self.trade_log_buffer:
                rows.append({
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
                })

            df_new = pd.DataFrame(rows)
            self.trade_log_buffer.clear()

        if os.path.exists(TRADE_LOG_PATH):
            try:
                df_old = pd.read_csv(TRADE_LOG_PATH)
            except Exception:
                df_old = pd.DataFrame()
            df = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df = df_new

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

        df["dedup_key"] = (
            df["timestamp"].astype(str)
            + "|" + df["symbol"].astype(str)
            + "|" + df["action"].astype(str)
            + "|" + df["ib_order_id"].astype(str)
        )
        df = df.drop_duplicates(subset=["dedup_key"]).drop(columns=["dedup_key"])

        # Ensure sorted by time for clean metrics & charts
        if "timestamp" in df.columns:
            df = df.sort_values("timestamp")

        df.to_csv(TRADE_LOG_PATH, index=False)

    def _write_heartbeat(self, status: str = "running", last_price: Optional[float] = None) -> None:
        data = {
            "app_name": APP_NAME,
            "symbol": SYMBOL,
            "status": status,
            "last_update": dt.datetime.utcnow().isoformat(),
            "position": self.current_position,
            "position_qty": self.current_qty,
            "entry_price": self.entry_price,
            "pnl": None,  # you can compute running PnL here if desired
            "last_price": last_price,
        }
        try:
            with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    # ─────────────────────────────
    # SAFETY & SIZING
    # ─────────────────────────────
    def _now(self) -> dt.datetime:
        # Always use UTC, timezone-naive, for consistent logging
        return dt.datetime.utcnow().replace(tzinfo=None)

    def _can_trade(self, action: str, price: float) -> bool:
        """
        Enforce:
        - Cooldown between trades
        - No repeated same side at nearly same price
        - Position-aware gating (simple long-only template)
        """
        now = self._now()

        # Cooldown
        if self.last_trade_time is not None:
            if (now - self.last_trade_time).total_seconds() < COOLDOWN_SEC:
                return False

        # Avoid repeating same action at similar price
        if self.last_action == action and self.last_action_price:
            last_px = self.last_action_price
            if last_px > 0:
                if abs(price - last_px) / last_px < MIN_SAME_ACTION_REPRICE:
                    return False

        # Simple long-only gating (extend for shorts if needed)
        if action == "BUY" and self.current_position == "LONG":
            # Already long — no pyramiding in this template
            return False
        if action == "SELL" and self.current_position == "NONE":
            # Nothing to sell
            return False

        return True

    def _qty_for_price(self, price: float) -> int:
        """
        Compute order quantity given a maximum capital constraint.
        Returns 0 if even MIN_QTY would exceed MAX_CAPITAL_PER_TRADE_USD.
        """
        if price <= 0:
            return 0
        max_qty = int(MAX_CAPITAL_PER_TRADE_USD // price)
        if max_qty < MIN_QTY:
            return 0
        return max_qty

    # ─────────────────────────────
    # STRATEGY LOGIC (YOU EDIT THIS)
    # ─────────────────────────────
    def compute_signal(self, price: float) -> Optional[str]:
        """
        Implement your existing trading logic here.

        MUST keep the same behaviour as your original strategy
        (same conditions, thresholds, lookbacks, etc.).

        Return:
            "BUY"  -> to open a LONG (if allowed)
            "SELL" -> to close a LONG (or go SHORT if you extend the logic)
            None   -> no action

        You can use self.prices or any custom attributes:
            self.prices.append(price)  # already done in _on_tick
        """
        # Example placeholder: do nothing
        return None

    # ─────────────────────────────
    # ORDER & EXECUTION HANDLING
    # ─────────────────────────────
    def _place_order(self, action: str, qty: int, price: float) -> None:
        order = MarketOrder(action, int(qty))
        if ACCOUNT_ID:
            order.account = ACCOUNT_ID

        trade: Trade = self.ib.placeOrder(self.contract, order)
        oid = trade.order.orderId
        log_status(f"Placed {action} MKT x{qty} @ ~{price:.4f} (orderId={oid})")

        # Track trade update events for fills
        trade.updateEvent += lambda t=trade: self._on_trade_update(t)

        # Update last trade info (even before fill)
        self.last_trade_time = self._now()
        self.last_action = action
        self.last_action_price = price

    def _on_trade_update(self, trade: Trade) -> None:
        """
        Called whenever IBKR updates orderStatus / fills.
        We log ONLY when the order is Filled or PartiallyFilled.
        """
        status = getattr(trade.orderStatus, "status", None)
        avg_price = getattr(trade.orderStatus, "avgFillPrice", None)
        filled = getattr(trade.orderStatus, "filled", None)
        oid = getattr(trade.order, "orderId", None)

        if oid is None:
            return

        # Ensure we only log once per filled order
        if self._logged_order_ids.get(oid, False):
            return

        if status is None:
            return

        status_lower = status.lower()
        if status_lower not in ("filled", "partiallyfilled"):
            return

        if avg_price is None or avg_price <= 0 or filled is None or filled <= 0:
            return

        action = trade.order.action.upper()
        qty = int(filled)
        price = float(avg_price)

        now = self._now()

        # Initialize before branch
        pnl = 0.0
        duration = 0.0
        position_after = self.current_position

        if action == "BUY":
            # Enter (or add) long — template assumes flat->long only
            self.current_position = "LONG"
            self.current_qty = qty
            self.entry_price = price
            self.entry_time = now
            position_after = self.current_position

        elif action == "SELL":
            # Close long
            if self.current_position == "LONG" and self.entry_price is not None:
                pnl = (price - float(self.entry_price)) * qty

            if self.entry_time is not None:
                duration = (now - self.entry_time).total_seconds()

            self.current_position = "NONE"
            self.current_qty = 0
            self.entry_price = None
            self.entry_time = None
            position_after = "NONE"

        # Ignore any other action type
        if action not in ("BUY", "SELL"):
            return

        # For BUY rows, duration remains 0, pnl remains 0
        row = TradeRow(
            timestamp=now,  # already UTC-naive
            symbol=SYMBOL,
            action=action,
            price=price,
            quantity=qty,
            pnl=pnl,
            duration=duration,
            position=position_after,
            status=status,
            ib_order_id=oid,
            extra={
                "avgFillPrice": avg_price,
                "filled": filled,
                "account": getattr(trade.order, "account", None),
            },
        )

        with self.lock:
            self.trade_log_buffer.append(row)
        self._flush_trade_log_buffer()

        self._logged_order_ids[oid] = True
        log_status(
            f"Logged fill: {action} x{qty} @ {price:.4f}, "
            f"status={status}, pnl={pnl:.2f}, pos={position_after}"
        )

    # ─────────────────────────────
    # MARKET DATA TICK HANDLER
    # ─────────────────────────────
    def _on_tick(self, _=None) -> None:
        if self._stop_requested:
            return
        if self._ticker is None:
            return

        price = (
            self._ticker.last
            or self._ticker.marketPrice()
            or self._ticker.close
            or 0.0
        )
        if price <= 0:
            return

        price = float(price)

        # Keep price history if you want indicators
        self.prices.append(price)
        if len(self.prices) > 10_000:
            self.prices = self.prices[-5_000:]

        action = self.compute_signal(price)
        if action not in ("BUY", "SELL"):
            self._write_heartbeat(status="running", last_price=price)
            return

        if not self._can_trade(action, price):
            self._write_heartbeat(status="running", last_price=price)
            return

        qty = self._qty_for_price(price)
        if qty <= 0:
            self._write_heartbeat(status="running", last_price=price)
            return

        self._place_order(action, qty, price)
        self._write_heartbeat(status="order_submitted", last_price=price)

    # ─────────────────────────────
    # MAIN LOOP
    # ─────────────────────────────
    def run(self) -> None:
        global CLIENT_ID
        while True:
            try:
                log_status(f"Connecting to IBKR at {HOST}:{PORT} (clientId={CLIENT_ID})")
                self.ib.connect(HOST, PORT, clientId=CLIENT_ID, readonly=False)
                self.ib.qualifyContracts(self.contract)
                log_status(f"Connected. Qualified contract: {self.contract}")
                break
            except Exception as e:
                msg = str(e).lower()
                if "client id already in use" in msg:
                    new_id = bump_client_id(name=APP_NAME, role="strategy")
                    CLIENT_ID = new_id
                    log_status(f"Client ID in use. Bumped to {new_id}, retrying...")
                    time.sleep(2)
                    continue
                else:
                    log_status(f"Fatal connection error: {e}")
                    self._write_heartbeat(status="error_connect")
                    return

        # Optional historical warmup (you can remove this if not needed)
        try:
            bars = self.ib.reqHistoricalData(
                self.contract,
                endDateTime="",
                durationStr=HIST_DURATION,
                barSizeSetting=HIST_BAR_SIZE,
                whatToShow=HIST_WHAT,
                useRTH=int(USE_RTH),
                formatDate=1,
                keepUpToDate=False,
            )
            log_status(f"Fetched {len(bars)} historical bars.")
        except Exception as e:
            log_status(f"Historical data request failed: {e}")

        # Subscribe to live data
        self._ticker = self.ib.reqMktData(self.contract, "", False, False)
        self._ticker.updateEvent += self._on_tick
        log_status("Subscribed to live market data.")

        self._write_heartbeat(status="running")

        try:
            while not self._stop_requested and self.ib.isConnected():
                self.ib.waitOnUpdate(timeout=0.5)
        except KeyboardInterrupt:
            log_status("KeyboardInterrupt received. Stopping runner.")
        except Exception as e:
            log_status(f"Exception in main loop: {e}")
        finally:
            try:
                self._write_heartbeat(status="stopped")
            except Exception:
                pass
            if self.ib.isConnected():
                log_status("Disconnecting from IBKR.")
                self.ib.disconnect()
            log_status("Runner stopped.")

    def stop(self) -> None:
        self._stop_requested = True


# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────
def main() -> None:
    runner = StrategyRunner()
    runner.run()


if __name__ == "__main__":
    main()
