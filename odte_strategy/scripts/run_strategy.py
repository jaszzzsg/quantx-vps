import sys
sys.path.insert(0, "/root/odte_strategy")

from ib_insync import *
from ib_spxw import get_spx_index, pick_spxw_chain, make_spx_option_from_chain
from datetime import datetime
import json, math, os
import pandas as pd

# =============================
# CONFIG (CHANGE HERE ONLY)
# =============================
MODE = "PAPER"  # PAPER or LIVE (keep PAPER for Bangkok week)
HOST = "127.0.0.1"

# TWS defaults:
PORT_PAPER = 4002
PORT_LIVE  = 7496

CLIENT_ID_PAPER = 1  # keep small int for IB; use DU id only as account field
ACCOUNT_PAPER   = os.getenv("IBKR_PAPER_ACCT", "DU9186063")  # set env var if you want

# Gates
ARM_JSON = "/root/projects/quantx_arm/state/regime_state.json"
RF_CSV   = "/root/odte_strategy/data/rf_daily_predictions.csv"

# Strategy toggles
RUN_BULL_PUT  = True
RUN_BEAR_CALL = False  # turn on later

# Bull Put params (baseline)
ENTRY_REF = "OPEN"          # or "LAST" etc; we can later use 13:30 snapshot
BPS_OTM_POINTS = 20
WIDTH = 5
BPS_LIMIT_CREDIT = 0.50     # example credit

# RF thresholds
RF_THR_BULLPUT  = 0.50
RF_THR_BEARCALL = 0.60

# Hard blocks
BULLPUT_BLOCK_REGIMES = {"R3"}

# =============================
# HELPERS
# =============================
def load_arm_state(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)

def load_rf_prob_for_today(path: str, ymd: str) -> float:
    df = pd.read_csv(path)
    # auto-detect columns
    date_col = [c for c in df.columns if "date" in c.lower()][0]
    prob_col = [c for c in df.columns if "prob" in c.lower()][0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce").dt.strftime("%Y-%m-%d")
    row = df[df[date_col] == ymd]
    if row.empty:
        return float("nan")
    return float(row.iloc[0][prob_col])

def connect_ib() -> IB:
    port = PORT_PAPER if MODE == "PAPER" else PORT_LIVE
    client_id = CLIENT_ID_PAPER
    ib = IB()
    ib.connect(HOST, port, clientId=client_id)
    if MODE == "PAPER":
        ib.reqMarketDataType(3)  # delayed ok for paper
    else:
        ib.reqMarketDataType(1)  # LIVE ONLY (no delayed)
    return ib

def get_spx_price(ib: IB) -> float:
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(spx)
    t = ib.reqMktData(spx, "", False, False)
    ib.sleep(2)
    px = t.open
    if math.isnan(px): px = t.last
    if math.isnan(px): px = t.close
    if math.isnan(px):
        return float(t.close) if not math.isnan(t.close) else 0.0  # fallback when market closed
    return float(px)

def get_today_expiry(ib: IB, spx_contract: Contract) -> str:
    chains = ib.reqSecDefOptParams(spx_contract.symbol, "", spx_contract.secType, spx_contract.conId)
    chain = next((c for c in chains if c.exchange == "CBOE" and c.tradingClass == "SPXW"), None) or next(c for c in chains if c.exchange == "CBOE")
    today = datetime.today().strftime("%Y%m%d")
    if today not in chain.expirations:
        raise RuntimeError("No SPX options expiring today.")
    return today, chain

def snap_to_5(x: float) -> int:
    return int(math.floor(x / 5) * 5)

def place_bull_put(ib: IB, expiry: str, spx_px: float):
    # short put = floor_to_5(spx_px) - 20 ; long put = short - 5
    short_strike = snap_to_5(spx_px) - BPS_OTM_POINTS
    long_strike  = short_strike - WIDTH

    # Resolve SPXW chain EVERY time before building legs
    spx_idx = get_spx_index(ib)
    chain = pick_spxw_chain(ib, spx_idx)

    sell_put = make_spx_option_from_chain(chain, expiry, short_strike, "P")
    buy_put  = make_spx_option_from_chain(chain, expiry, long_strike,  "P")
    ib.qualifyContracts(sell_put, buy_put)
    assert sell_put.conId != 0 and buy_put.conId != 0, "SPXW qualify failed: conId=0"
    spread = Bag(
        symbol="SPX",
        exchange=chain.exchange,
        currency="USD",
        comboLegs=[
            ComboLeg(conId=sell_put.conId, ratio=1, action="SELL", exchange=chain.exchange),
            ComboLeg(conId=buy_put.conId,  ratio=1, action="BUY",  exchange=chain.exchange),
        ],
    )

    order = LimitOrder(
        action="SELL",
        totalQuantity=1,
        lmtPrice=BPS_LIMIT_CREDIT,
        account=ACCOUNT_PAPER if MODE == "PAPER" else "",  # optional for live if you prefer default
    )

    trade = ib.placeOrder(spread, order)
    ib.sleep(1)
    print(f"✅ BULL PUT ORDER SENT | expiry={expiry} short={short_strike} long={long_strike} credit={BPS_LIMIT_CREDIT}")
    print(f"   status={trade.orderStatus.status}")
    return trade

# =============================
# MAIN
# =============================
def main():
    ymd = datetime.utcnow().strftime("%Y-%m-%d")
    print(f"=== RUN_STRATEGY | MODE={MODE} | date={ymd} ===")

    arm = load_arm_state(ARM_JSON)
    regime = arm.get("regime", "NA")
    blocked_today = set(arm.get("blocked_strategies_today", []) or [])
    print(f"ARM: regime={regime} blocked_today={blocked_today}")

    rf_prob = load_rf_prob_for_today(RF_CSV, ymd)
    print(f"RF: prob_safe={rf_prob}")

    # --- Bull Put gating ---
    allow_bullput = RUN_BULL_PUT
    if "BULL_PUT" in blocked_today:
        allow_bullput = False
        print("SKIP BULL_PUT: blocked_strategies_today")
    if regime in BULLPUT_BLOCK_REGIMES:
        allow_bullput = False
        print(f"SKIP BULL_PUT: regime {regime} hard-blocked")
    if not math.isnan(rf_prob) and rf_prob < RF_THR_BULLPUT:
        allow_bullput = False
        print(f"SKIP BULL_PUT: RF prob {rf_prob:.3f} < {RF_THR_BULLPUT}")

    if not allow_bullput:
        print("DONE: No trades allowed today.")
        return

    # --- Execute (paper) ---
    ib = connect_ib()
    try:
        spx_px = get_spx_price(ib)
        if spx_px <= 0:
            print("SKIP: SPX price unavailable (no market data).")
            from utils.tg_notify import notify_skip
            notify_skip("BULL_PUT","SPX","SPX price unavailable (no market data)")
            return

        print(f"SPX ref price={spx_px:.2f}")
        spx = Index("SPX", "CBOE", "USD")
        ib.qualifyContracts(spx)
        expiry, _ = get_today_expiry(ib, spx)
        place_bull_put(ib, expiry, spx_px)
    finally:
        ib.disconnect()

if __name__ == "__main__":
    main()
