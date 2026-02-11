from ib_insync import Index, Option

def get_spx_index(ib):
    spx = Index("SPX", "CBOE", "USD")
    ib.qualifyContracts(spx)
    return spx

def pick_spxw_chain(ib, spx_index):
    chains = ib.reqSecDefOptParams(spx_index.symbol, "", spx_index.secType, spx_index.conId)
    chain = next((c for c in chains if getattr(c, "tradingClass", None) == "SPXW"), None) or \
            next((c for c in chains if getattr(c, "tradingClass", None) == "SPX"), None) or \
            chains[0]
    return chain

def make_spx_option_from_chain(chain, expiry, strike, right):
    """
    Builds an SPX option using the resolved chain params.
    IMPORTANT: tradingClass/exchange/multiplier comes from chain (SPXW preferred).
    """
    return Option(
        symbol="SPX",
        lastTradeDateOrContractMonth=str(expiry),
        strike=float(strike),
        right=str(right),
        exchange=chain.exchange,
        tradingClass=chain.tradingClass,
        multiplier=chain.multiplier,
    )
