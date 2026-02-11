from ib_insync import IB, Index, Option

HOST, PORT, CID = "127.0.0.1", 4002, 707
EXPIRY = "20251222"
RIGHT = "P"
STRIKE = 6000

ib = IB()
ib.connect(HOST, PORT, clientId=CID, timeout=10)
print("CONNECTED:", ib.isConnected())

spx = Index("SPX", "CBOE", "USD")
ib.qualifyContracts(spx)

chains = ib.reqSecDefOptParams(spx.symbol, "", spx.secType, spx.conId)

chain = next((c for c in chains if c.tradingClass == "SPXW"), None) or \
        next((c for c in chains if c.tradingClass == "SPX"), None) or chains[0]

print(f"Chain picked: exch={chain.exchange} tradingClass={chain.tradingClass} mult={chain.multiplier}")

opt = Option(
    symbol="SPX",
    lastTradeDateOrContractMonth=EXPIRY,
    strike=float(STRIKE),
    right=RIGHT,
    exchange=chain.exchange,
    tradingClass=chain.tradingClass,
    multiplier=chain.multiplier
)

ib.qualifyContracts(opt)
print(f"Test option: {opt.lastTradeDateOrContractMonth} {opt.strike} {opt.right} => conId: {opt.conId}")
print("Qualified:", opt.conId != 0)

ib.disconnect()
