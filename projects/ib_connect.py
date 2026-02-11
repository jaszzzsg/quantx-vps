import os
from pathlib import Path
from ib_insync import IB

ENV_KEYS = ("IB_HOST", "IB_PORT", "IB_CLIENT_ID", "IB_MODE")

def clear_env_keys():
    for k in ENV_KEYS:
        os.environ.pop(k, None)

def load_env(env_path: str, overwrite: bool = True):
    p = Path(env_path)
    if not p.exists():
        raise FileNotFoundError(f"Missing env file: {env_path}")

    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if overwrite:
            os.environ[k] = v
        else:
            os.environ.setdefault(k, v)

def connect_from_env(env_path: str, timeout: int = 8) -> tuple[IB, str]:
    # ensure each run is isolated even in same process
    clear_env_keys()
    load_env(env_path, overwrite=True)

    host = os.environ.get("IB_HOST", "127.0.0.1")
    port = int(os.environ["IB_PORT"])
    client_id = int(os.environ.get("IB_CLIENT_ID", "991"))
    mode = os.environ.get("IB_MODE", "UNKNOWN").upper()

    print("=" * 70)
    print(f"IB CONNECT  | MODE={mode} | HOST={host} | PORT={port} | CLIENT_ID={client_id}")
    print("=" * 70)

    ib = IB()
    ib.connect(host, port, clientId=client_id, timeout=timeout)

    accts = ib.managedAccounts()
    if not accts:
        ib.disconnect()
        raise RuntimeError("Connected but managedAccounts() is empty. Something is off.")

    acct = accts[0]
    print(f"CONNECTED ✅  serverVersion={ib.client.serverVersion()}  accounts={accts}")

    # Safety gating
    if mode == "LIVE" and not acct.startswith("U"):
        ib.disconnect()
        raise RuntimeError(f"SAFETY STOP: MODE=LIVE but account is {acct} (expected U...)")

    if mode == "PAPER" and not acct.startswith("DU"):
        ib.disconnect()
        raise RuntimeError(f"SAFETY STOP: MODE=PAPER but account is {acct} (expected DU...)")

    return ib, acct

if __name__ == "__main__":
    for env in ("/root/projects/.env_live", "/root/projects/.env_paper"):
        try:
            ib, acct = connect_from_env(env)
        except Exception as e:
            print(f"TEST FAILED ❌  env={env}  err={type(e).__name__}: {e}")
        else:
            ib.disconnect()
            print(f"DISCONNECTED ✅  acct={acct}")
        print()
