import time, math, json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from ib_insync import IB, Index, Option, Bag, ComboLeg, LimitOrder, TagValue

MIN_CREDIT = 1.00
NY = ZoneInfo("America/New_York")
UTC = timezone.utc


def is_bad_px(x):
    return x is None or (isinstance(x, float) and (math.isnan(x) or x <= 0))


def spread_mid_credit(ib, short_leg, long_leg):
    try:
        t1 = ib.reqMktData(short_leg, "", False, False)
        t2 = ib.reqMktData(long_leg, "", False, False)
        ib.sleep(1.0)

        if is_bad_px(t1.bid) or is_bad_px(t1.ask) or is_bad_px(t2.bid) or is_bad_px(t2.ask):
            return None

        return round(((t1.bid + t1.ask) / 2) - ((t2.bid + t2.ask) / 2), 2)
    except Exception:
        return None


def run():
    ib = IB()
    try:
        ib.connect("127.0.0.1", 4002, clientId=711, timeout=8)

        with open("/root/odte_strategy/state/spcfd.json") as f:
            anchor = json.load(f)

        ref_px = float(anchor["value"])
        print(f"[PUT] SPCFD={ref_px}")

        now = datetime.now(NY)
        entry = now.replace(hour=13, minute=30, second=0, microsecond=0)
        cutoff = now.replace(hour=15, minute=20, second=0, microsecond=0)

        if now < entry or now > cutoff:
            print("[PUT] Outside trade window")
            return

        spx = Index("SPX", "CBOE", "USD")
        ib.qualifyContracts(spx)

        expiry = now.strftime("%Y%m%d")
        short_strike = int(ref_px // 5 * 5 - 20)
        long_strike = short_strike - 5

        short_put = Option("SPX", expiry, short_strike, "P", "CBOE", tradingClass="SPXW")
        long_put = Option("SPX", expiry, long_strike, "P", "CBOE", tradingClass="SPXW")
        ib.qualifyContracts(short_put, long_put)

        bag = Bag(
            symbol="SPX",
            exchange="CBOE",
            currency="USD",
            comboLegs=[
                ComboLeg(conId=short_put.conId, ratio=1, action="SELL", exchange="CBOE"),
                ComboLeg(conId=long_put.conId, ratio=1, action="BUY", exchange="CBOE"),
            ],
        )

        mid = spread_mid_credit(ib, short_put, long_put)
        credit = MIN_CREDIT if is_bad_px(mid) else max(MIN_CREDIT, round(mid, 2))

        print(f"[PUT] mid={mid} → credit={credit}")

        order = LimitOrder("SELL", 1, credit)
        order.smartComboRoutingParams = [TagValue("NonGuaranteed", "1")]
        trade = ib.placeOrder(bag, order)

        while True:
            st = trade.orderStatus.status
            print(f"[PUT] HOLD credit={credit} status={st}")
            if st == "Filled":
                print("[PUT] FILLED")
                return
            time.sleep(120)

    finally:
        try:
            ib.disconnect()
        except Exception:
            pass
