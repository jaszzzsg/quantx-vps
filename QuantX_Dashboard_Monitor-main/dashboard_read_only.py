import os
import sys
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional, List

import numpy as np
import pandas as pd
import streamlit as st

# Optional logo support
try:
    from PIL import Image
    _PIL_AVAILABLE = True
except Exception:
    _PIL_AVAILABLE = False

# Optional charts
try:
    import altair as alt
    _ALT_AVAILABLE = True
except Exception:
    _ALT_AVAILABLE = False

from dotenv import load_dotenv
from utils.performance_metrics import calculate_metrics
from utils.client_id_manager import get_or_allocate_client_id


# ============================================================
# Load .env
# ============================================================
load_dotenv()

START_EQUITY = float(os.getenv("START_EQUITY", "10000"))
MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "-1000"))
APP_ENV = os.getenv("APP_ENV", "local")
DASHBOARD_TIMEZONE = os.getenv("DASHBOARD_TIMEZONE", "US/Eastern")
LOG_ROOT = os.getenv("LOG_ROOT", "strategies_runner/logs")


# ============================================================
# Streamlit Config
# ============================================================
st.set_page_config(page_title="Quant X Dashboard (Read-Only)", layout="wide")

LOGO_PATH = os.path.join("assets", "logo.png")
US_ET = ZoneInfo("America/New_York")

EXPECTED_COLUMNS = [
    "timestamp", "symbol", "action", "price", "quantity",
    "pnl", "duration", "position", "status", "ib_order_id"
]


# ============================================================
# Discover strategy logs (AUTO-DETECT STRATEGIES)
# ============================================================
def discover_strategy_logs(log_root: str) -> Dict[str, str]:
    """
    AUTO-DETECT:
        LOG_ROOT/
            StrategyName/
                trade_log.csv
    Returns:
        { "ME_RANK1": "path/to/trade_log.csv", ... }
    """
    strategies: Dict[str, str] = {}

    if not os.path.isdir(log_root):
        return strategies

    for name in sorted(os.listdir(log_root)):
        strategy_dir = os.path.join(log_root, name)
        if not os.path.isdir(strategy_dir):
            continue

        trade_log_path = os.path.join(strategy_dir, "trade_log.csv")
        if os.path.exists(trade_log_path):
            strategies[name] = trade_log_path

    return strategies


# ============================================================
# Trade log loader
# ============================================================
def load_trade_log(path: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(path)
        if df.empty:
            return pd.DataFrame(columns=EXPECTED_COLUMNS)
    except Exception as e:
        st.warning(f"Failed to load trade log: {path} ({e})")
        return pd.DataFrame(columns=EXPECTED_COLUMNS)

    df = df.copy()

    # Ensure required columns
    for c in EXPECTED_COLUMNS:
        if c not in df.columns:
            df[c] = np.nan

    # Parse timestamp & ensure timezone-naive
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce").dt.tz_localize(None)

    # Type conversions
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("Int64")
    df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce")

    df = df.sort_values("timestamp").reset_index(drop=True)
    return df


# ============================================================
# Helper functions
# ============================================================
def _local_now():
    return datetime.now().astimezone()

def _format_local_tz(dt):
    offset = dt.utcoffset() or timedelta(0)
    sign = "+" if offset >= timedelta(0) else "-"
    minutes = int(abs(offset.total_seconds()) // 60)
    hh, mm = divmod(minutes, 60)
    return f"UTC{sign}{hh:02d}:{mm:02d}"

def _format_td(delta):
    secs = int(max(0, delta.total_seconds()))
    h, r = divmod(secs, 3600)
    m, _ = divmod(r, 60)
    return f"{h}h {m}m"


# ============================================================
# Sidebar
# ============================================================
st.sidebar.header("Settings")
st.sidebar.caption(f"Environment: `{APP_ENV}`")
st.sidebar.caption(f"Log Root: `{LOG_ROOT}`")

st.sidebar.subheader("Market Clock")
now = _local_now()
st.sidebar.caption(f"Local: {now:%Y-%m-%d %H:%M:%S} ({_format_local_tz(now)})")
st.sidebar.caption("(Timestamps in logs are assumed UTC)")


# ============================================================
# Discover all strategies automatically
# ============================================================
strategies = discover_strategy_logs(LOG_ROOT)

if not strategies:
    st.warning("No strategy logs found. Add folders containing trade_log.csv.")
    st.stop()


# ============================================================
# Load trade logs & compute metrics
# ============================================================
strategy_frames: Dict[str, pd.DataFrame] = {}
metrics_by_strategy: Dict[str, Dict[str, Any]] = {}
summary_rows = []

total_closed = 0
total_trades = 0
today_utc = pd.Timestamp.utcnow().normalize().replace(tzinfo=None)
todays_pnl = 0.0

for name, path in strategies.items():

    df = load_trade_log(path)
    strategy_frames[name] = df

    # Calculate metrics
    if not df.empty:
        try:
            m = calculate_metrics(df, price_lookup=None, start_equity=START_EQUITY)
        except Exception as e:
            st.warning(f"Metrics failed for {name}: {e}")
            m = {}
    else:
        m = {}

    metrics_by_strategy[name] = m

    closed = float(m.get("closed_pl", 0))
    total_closed += closed
    total_trades += int(m.get("number_of_trades", 0))

    # Today P/L
    if not df.empty:
        _df = df.copy()
        # already timezone-naive by loader
        todays_df = _df[_df["timestamp"] >= today_utc]
        todays_pnl += pd.to_numeric(todays_df["pnl"], errors="coerce").fillna(0).sum()

    # Client ID (informational only)
    client_id = get_or_allocate_client_id(name=name, role="strategy")

    summary_rows.append({
        "Strategy": name,
        "Client ID": client_id,
        "Closed P/L": round(closed, 2),
        "Open P/L": round(float(m.get("open_pl", 0)), 2),
        "Total P/L": round(closed + float(m.get("open_pl", 0)), 2),
        "Win Rate (%)": round(m.get("win_rate", 0), 2),
        "Profit Factor": round(m.get("profit_factor", 0), 2),
        "CAGR (%)": round(m.get("cagr", 0) * 100, 2),
        "Max DD": round(m.get("max_drawdown", 0), 2),
        "Trades": int(m.get("number_of_trades", 0)),
    })


# ============================================================
# Portfolio Overview
# ============================================================
st.title("Quant X Dashboard")

col1, col2, col3 = st.columns(3)
col1.metric("Closed P&L", f"${total_closed:,.2f}")
col2.metric("Today's P&L", f"${todays_pnl:,.2f}")
col3.metric("Total Trades", str(total_trades))

if todays_pnl <= MAX_DAILY_LOSS:
    st.error(f"Daily loss limit exceeded: {todays_pnl:.2f} ≤ {MAX_DAILY_LOSS}")


# ============================================================
# Summary Table
# ============================================================
st.subheader("📊 Performance Summary")

summary_df = pd.DataFrame(summary_rows)
st.dataframe(summary_df, use_container_width=True, hide_index=True)

st.download_button(
    "Download Summary CSV",
    summary_df.to_csv(index=False).encode("utf-8"),
    "summary.csv",
    "text/csv"
)


# ============================================================
# Detailed Views
# ============================================================
st.subheader("📂 Detailed Strategy Logs")

for name, df in strategy_frames.items():

    with st.expander(f"📂 {name}", expanded=False):

        st.write("### Trade Log")

        if df.empty:
            st.info("No trades recorded yet.")
            continue

        st.dataframe(df.sort_values("timestamp", ascending=False),
                     use_container_width=True, hide_index=True)

        st.download_button(
            f"Download {name} Trades",
            df.to_csv(index=False).encode("utf-8"),
            f"{name}_trade_log.csv",
            "text/csv"
        )

        # Charts
        if "pnl" in df.columns and not df.empty:
            df2 = df.copy()
            df2["timestamp"] = pd.to_datetime(df2["timestamp"], errors="coerce").dt.tz_localize(None)

            st.write("### Equity Curve")
            eq = df2[["timestamp", "pnl"]].copy()
            eq["cumulative"] = eq["pnl"].cumsum()
            st.line_chart(eq.set_index("timestamp")["cumulative"])

            st.write("### Drawdown")
            dd = eq.copy()
            dd["drawdown"] = dd["cumulative"].cummax() - dd["cumulative"]
            st.area_chart(dd.set_index("timestamp")["drawdown"])

