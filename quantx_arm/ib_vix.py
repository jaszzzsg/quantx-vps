from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import json

from ib_insync import IB, Index

@dataclass
class VixResult:
    ok: bool
    vix: Optional[float]
    vix_ma: Optional[float]
    asof: Optional[str]
    source: str
    note: str = ""

def fetch_vix_from_ib(
    host: str = "127.0.0.1",
    port: int = 4002,
    client_id: int = 991,
    timeout: float = 6.0,
    ma_period: int = 20
) -> VixResult:
    """
    Fetch latest daily VIX close + 20-day MA from IB.
    Requests 1 month of daily bars to compute true rolling MA.
    This function NEVER raises to caller.
    """
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=timeout)

        contract = Index("VIX", "CBOE")
        ib.qualifyContracts(contract)

        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="1 M",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1
        )

        if not bars:
            return VixResult(False, None, None, None, f"IB:{host}:{port}", "No bars returned")

        last = bars[-1]
        if last.close is None:
            return VixResult(False, None, None, str(last.date), f"IB:{host}:{port}", "Close is None")

        # Compute 20-day MA from returned bars
        closes = [b.close for b in bars if b.close is not None]
        if len(closes) >= ma_period:
            vix_ma = sum(closes[-ma_period:]) / ma_period
        elif len(closes) > 0:
            vix_ma = sum(closes) / len(closes)  # partial MA if insufficient history
        else:
            vix_ma = None

        return VixResult(
            ok=True,
            vix=float(last.close),
            vix_ma=float(vix_ma) if vix_ma is not None else None,
            asof=str(last.date),
            source=f"IB:{host}:{port}",
            note="OK"
        )

    except Exception as e:
        return VixResult(
            ok=False,
            vix=None,
            vix_ma=None,
            asof=None,
            source=f"IB:{host}:{port}",
            note=f"{type(e).__name__}: {e}"
        )
    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    r = fetch_vix_from_ib()
    print(json.dumps(r.__dict__, indent=2))
