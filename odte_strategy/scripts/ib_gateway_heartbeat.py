import time
from datetime import datetime
from ib_insync import IB

HOST = "127.0.0.1"
PORT = 4002
CLIENT_ID_BASE = 700  # avoids clashes
LOOPS = 30            # 30 * 10s = ~5 minutes
SLEEP_SEC = 10

def ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def main():
    print(f"[{ts()}] HEARTBEAT START  host={HOST} port={PORT} loops={LOOPS} every={SLEEP_SEC}s")
    for i in range(LOOPS):
        ib = IB()
        cid = CLIENT_ID_BASE + i
        try:
            ib.connect(HOST, PORT, clientId=cid, timeout=5)
            ok = ib.isConnected()
            sv = ib.client.serverVersion() if ok else None
            accts = ib.managedAccounts() if ok else []
            # lightweight API call
            cur = ib.reqCurrentTime()
            print(f"[{ts()}] #{i:02d} CONNECT ok={ok} serverVer={sv} accounts={accts} ibTime={cur}")
        except Exception as e:
            print(f"[{ts()}] #{i:02d} FAIL {type(e).__name__}: {e}")
            return 2
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass
        time.sleep(SLEEP_SEC)

    print(f"[{ts()}] HEARTBEAT PASS ✅")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
