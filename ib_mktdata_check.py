import os
from dataclasses import dataclass
from pathlib import Path
from ib_insync import IB, Index, util

@dataclass
class Cfg:
    mode: str
    host: str
    port: int
    client_id: int

def load_env(path: str) -> Cfg:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    env = {}
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    mode = env.get("IB_MODE") or env.get("MODE") or ""
    host = env.get("IB_HOST", "127.0.0.1")
    port = int(env.get("IB_PORT", "4001"))
    cid = int(env.get("IB_CLIENT_ID", "1"))
    return Cfg(mode=mode.upper(), host=host, port=port, client_id=cid)

def check(env_path: str):
    cfg = load_env(env_path)
    print("\n" + "="*70)
    print(f"MARKET DATA CHECK | env={env_path} | MODE={cfg.mode} | {cfg.host}:{cfg.port} | clientId={cfg.client_id}")
    print("="*70)

    ib = IB()
    try:
        ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=8)
        print("CONNECTED ✅", "serverVersion=", ib.client.serverVersion(), "managedAccounts=", ib.managedAccounts())

        # Use SPX index (CBOE). On weekend you may get no real-time ticks; that's OK.
        spx = Index("SPX", "CBOE", "USD")
        ib.qualifyContracts(spx)

        # Request snapshot market data
        t = ib.reqMktData(spx, "", snapshot=True, regulatorySnapshot=False)
        ib.sleep(2.0)

        # Print whatever fields we have (may be NaN / None / -1 on weekend)
        print("SNAPSHOT:")
        print("  last=", t.last, "close=", t.close, "bid=", t.bid, "ask=", t.ask)

        # Tiny historical pull (should work if permissions OK)
        bars = ib.reqHistoricalData(
            spx,
            endDateTime="",
            durationStr="2 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=False,
            formatDate=1
        )
        if bars:
            last = bars[-1]
            print("HISTORICAL ✅ lastBar:", last.date, "close=", last.close)
        else:
            print("HISTORICAL ⚠️ got 0 bars")

    except Exception as e:
        print("FAILED ❌", type(e).__name__, str(e))
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass
        print("DISCONNECTED ✅")

def main():
    # We test both gateways using your env files created earlier
    for p in ("/root/projects/.env_live", "/root/projects/.env_paper"):
        check(p)

if __name__ == "__main__":
    main()
