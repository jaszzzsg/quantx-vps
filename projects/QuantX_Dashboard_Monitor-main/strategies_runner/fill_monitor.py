# =========================================================
# Fill Monitor — hourly intraday fill checker
# Runs 10am–4pm ET via cron (15:00–21:00 UTC Mon–Fri)
#
# For each strategy with a TRADE_ENTER today (filled=0):
#   - Connect to IBKR, reqExecutions()
#   - Match short-leg fill to strategy entry
#   - Append TRADE_FILL row + Telegram if new fill found
#   - Silent exit if nothing to do
#
# Generic: works for any alpha with trade_log.csv
# =========================================================

import os
import sys
import csv
import json
import time
import glob
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ib_insync import IB, ExecutionFilter

BASE_PATH = "/root/projects/QuantX_Dashboard_Monitor-main"
sys.path.append(BASE_PATH)

from utils.client_id_manager import get_client_id
from utils.tg_notify import tg_send

IB_HOST    = "127.0.0.1"
IB_PORT    = 4002
IB_ACCOUNT = "DUP148773"
ET         = ZoneInfo("America/New_York")

LOG_ROOT = f"{BASE_PATH}/strategies_runner/logs"


def utc_now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def trade_date_et() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")

def today_expiry() -> str:
    """Today's date in YYYYMMDD format (IBKR expiry format)."""
    return datetime.now(ET).strftime("%Y%m%d")


def load_trade_logs(trade_date: str) -> list[dict]:
    """
    Scan all strategy trade_log.csv files.
    Return list of TRADE_ENTER rows from today that are not yet filled.
    Each dict includes the source log path and parsed details.
    """
    entries = []
    pattern = os.path.join(LOG_ROOT, "*", "trade_log.csv")
    for log_path in glob.glob(pattern):
        strategy_name = os.path.basename(os.path.dirname(log_path))
        if not os.path.isfile(log_path):
            continue
        try:
            with open(log_path, "r", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("action") != "TRADE_ENTER":
                        continue
                    ts = row.get("timestamp_utc", "")
                    # Match today by trade date in details or timestamp date
                    details_raw = row.get("details", "{}")
                    try:
                        details = json.loads(details_raw)
                    except Exception:
                        details = {}
                    expiry = details.get("expiry", "")
                    if expiry != today_expiry():
                        continue
                    # Skip if already marked filled (filled=1 in details)
                    if int(details.get("filled", 0)) >= 1:
                        continue
                    entries.append({
                        "log_path": log_path,
                        "strategy": strategy_name,
                        "alpha_id": row.get("alpha_id", ""),
                        "regime": row.get("regime", ""),
                        "rf_prob": row.get("rf_prob", ""),
                        "details": details,
                        "expiry": expiry,
                        # underlying defaults to SPX for backward compat with old log rows
                        "underlying": details.get("underlying", "SPX"),
                        # short leg strike + right
                        "short_strike": details.get("short_call") or details.get("short_put"),
                        "right": "C" if "short_call" in details else "P",
                    })
        except Exception as e:
            print(f"[WARN] Could not read {log_path}: {e}")
    return entries


def already_filled_in_log(log_path: str, expiry: str) -> bool:
    """Return True if TRADE_FILL already logged for today's expiry."""
    if not os.path.isfile(log_path):
        return False
    with open(log_path, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("action") != "TRADE_FILL":
                continue
            try:
                d = json.loads(row.get("details", "{}"))
                if d.get("expiry") == expiry:
                    return True
            except Exception:
                pass
    return False


def append_fill_row(log_path: str, alpha_id: str, regime: str, rf_prob: str, details: dict):
    """Append a TRADE_FILL row to the strategy trade log."""
    with open(log_path, "a", newline="") as f:
        w = csv.writer(f)
        w.writerow([utc_now_str(), alpha_id, "TRADE_FILL", regime, rf_prob, json.dumps(details)])


def get_executions(ib: IB, expiry: str) -> list:
    """Return all option executions for today's expiry across all underlyings."""
    filt = ExecutionFilter(acctCode=IB_ACCOUNT)   # no symbol filter — works for any ticker
    fills = ib.reqExecutions(filt)
    result = []
    for fill in fills:
        c = fill.contract
        e = fill.execution
        if getattr(c, "lastTradeDateOrContractMonth", "") == expiry:
            result.append({
                "symbol": c.symbol,        # underlying ticker e.g. SPX, NDX, SPY
                "strike": c.strike,
                "right": c.right,          # 'C' or 'P'
                "side": e.side,            # 'SLD' or 'BOT'
                "shares": e.shares,
                "price": e.avgPrice,
                "exec_id": e.execId,
                "order_id": e.orderId,
                "time": e.time,
            })
    return result


def match_fill(executions: list, underlying: str, short_strike, right: str) -> dict | None:
    """
    Find the short-leg fill for this strategy.
    Short leg = SELL (SLD) the given underlying + strike + right.
    Returns the execution dict if found, else None.
    """
    if short_strike is None:
        return None
    for ex in executions:
        if (ex["symbol"] == underlying
                and ex["right"] == right
                and ex["side"] == "SLD"
                and float(ex["strike"]) == float(short_strike)):
            return ex
    return None


def main():
    trade_date = trade_date_et()
    expiry = today_expiry()

    # Load all unfilled TRADE_ENTER rows for today
    pending = load_trade_logs(trade_date)

    if not pending:
        print(f"[FILL_MONITOR] {utc_now_str()} — no pending TRADE_ENTER for {trade_date}, exiting.")
        return

    print(f"[FILL_MONITOR] {utc_now_str()} — checking {len(pending)} pending entries for {trade_date}")

    # Connect to IBKR once
    try:
        client_id = get_client_id(IB_HOST, IB_PORT, purpose="fill_monitor", project="quantx_strategies")
        ib = IB()
        ib.connect(IB_HOST, IB_PORT, clientId=client_id, readonly=True, timeout=10)
    except Exception as e:
        print(f"[FILL_MONITOR] IB connect failed: {e}")
        return

    try:
        executions = get_executions(ib, expiry)
        print(f"[FILL_MONITOR] {len(executions)} SPX executions found for expiry {expiry}")

        for entry in pending:
            log_path     = entry["log_path"]
            strategy     = entry["strategy"]
            alpha_id     = entry["alpha_id"]
            short_strike = entry["short_strike"]
            right        = entry["right"]
            underlying   = entry["underlying"]
            details      = entry["details"]

            # Skip if already recorded in log (safe re-run)
            if already_filled_in_log(log_path, expiry):
                print(f"[FILL_MONITOR] {strategy} already has TRADE_FILL for {expiry}, skipping.")
                continue

            matched = match_fill(executions, underlying, short_strike, right)
            if matched is None:
                print(f"[FILL_MONITOR] {strategy} — no fill yet (short {right}{short_strike})")
                continue

            # Fill confirmed — log + notify
            fill_details = {
                "expiry": expiry,
                "short_strike": short_strike,
                "right": right,
                "fill_price": matched["price"],
                "fill_qty": matched["shares"],
                "fill_time": str(matched["time"]),
                "exec_id": matched["exec_id"],
                "order_id": matched["order_id"],
                # carry over original spread details
                "short_call": details.get("short_call"),
                "long_call":  details.get("long_call"),
                "short_put":  details.get("short_put"),
                "long_put":   details.get("long_put"),
                "credit":     details.get("credit"),
            }
            append_fill_row(log_path, alpha_id, entry["regime"], entry["rf_prob"], fill_details)
            print(f"[FILL_MONITOR] ✅ TRADE_FILL logged for {strategy}")

            # Telegram
            spread_type = "BEAR_CALL" if right == "C" else "BULL_PUT"
            long_strike = details.get("long_call") or details.get("long_put")
            msg = (
                f"🎯 FILLED\n"
                f"SPX {spread_type}\n"
                f"Expiry: {expiry}\n"
                f"Spread: {short_strike}/{long_strike}\n"
                f"Fill price: {matched['price']}\n"
                f"Qty: {int(matched['shares'])}\n"
                f"Fill time: {matched['time']}\n"
                f"Time: {utc_now_str()}"
            )
            tg_send(msg)
            print(f"[FILL_MONITOR] Telegram sent for {strategy}")

    except Exception as e:
        print(f"[FILL_MONITOR] Error: {e}")
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    main()
