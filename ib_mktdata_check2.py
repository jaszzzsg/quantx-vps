from dataclasses import dataclass
from pathlib import Path
from ib_insync import IB, Index, Stock
import math
import time

@dataclass
class Cfg:
    mode: str
    host: str
    port: int
    client_id: int

def load_env(path: str) -> Cfg:
    p = Path(path)
    env = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    mode = (env.get("IB_MODE") or env.get("MODE") or "").upper()
    host = env.get("IB_HOST", "127.0.0.1")
    port = int(env.get("IB_PORT", "4001"))
    cid  = int(env.get("IB_CLIENT_ID", "1"))
    return Cfg(mode, host, port, cid)

def fmt(x):
    if x is None: return "None"
    try:
        if isinstance(x, float) and (math.isnan(x) or math.isinf(x)):
            return "nan"
    except: pass
    return str(x)

def run_one(env_path: str):
    cfg = load_env(env_path)
    print("\n" + "="*78)
    print(f"MKT DATA TYPE CHECK | env={env_path} | MODE={cfg.mode} | {cfg.host}:{cfg.port} | clientId={cfg.client_id}")
    print("="*78)

    ib = IB()
    errors = []

    def on_error(reqId, errorCode, errorString, contract):
        # keep it short but useful
        errors.append((reqId, errorCode, errorString))
    ib.errorEvent += on_error

    try:
        ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=8)
        print("CONNECTED ✅", "managedAccounts=", ib.managedAccounts())

        # Use SPY as a “clean” market data permission test during market hours.
        # On weekend it will still likely show nan, but we can see if IB reports delayed/frozen permissions.
        spy = Stock("SPY", "ARCA", "USD")
        spx = Index("SPX", "CBOE", "USD")
        ib.qualifyContracts(spy, spx)

        for md_type, label in [(1, "LIVE"), (2, "FROZEN"), (3, "DELAYED"), (4, "DELAYED_FROZEN")]:
            errors.clear()
            ib.reqMarketDataType(md_type)

            t_spy = ib.reqMktData(spy, "", snapshot=False)
            t_spx = ib.reqMktData(spx, "", snapshot=False)

            ib.sleep(2.5)

            print(f"\n[{label}] (reqMarketDataType={md_type})")
            print(" SPY:", "mdType=", fmt(getattr(t_spy, "marketDataType", None)),
                  "bid=", fmt(t_spy.bid), "ask=", fmt(t_spy.ask), "last=", fmt(t_spy.last), "close=", fmt(t_spy.close))
            print(" SPX:", "mdType=", fmt(getattr(t_spx, "marketDataType", None)),
                  "bid=", fmt(t_spx.bid), "ask=", fmt(t_spx.ask), "last=", fmt(t_spx.last), "close=", fmt(t_spx.close))

            # cancel streams
            ib.cancelMktData(spy)
            ib.cancelMktData(spx)
            ib.sleep(0.2)

            if errors:
                # show last few unique error codes (most useful)
                uniq = []
                for e in errors:
                    if e not in uniq:
                        uniq.append(e)
                print(" Errors:", uniq[-5:])
            else:
                print(" Errors: (none)")

        print("\nNOTE: On Saturday, prices will often be nan. What matters is:")
        print(" - whether errors show 'No market data permissions' vs delayed/frozen types")
        print(" - and on next trading day, LIVE should start printing real bid/ask/last")

    except Exception as e:
        print("FAILED ❌", type(e).__name__, str(e))
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass
        print("DISCONNECTED ✅")

def main():
    for p in ("/root/projects/.env_live", "/root/projects/.env_paper"):
        run_one(p)

if __name__ == "__main__":
    main()
