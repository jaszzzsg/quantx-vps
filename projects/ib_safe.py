import os
from pathlib import Path
from dataclasses import dataclass
from ib_insync import IB

ENV_KEYS = ("IB_HOST", "IB_PORT", "IB_CLIENT_ID", "IB_MODE")

def clear_env_keys():
    for k in ENV_KEYS:
        os.environ.pop(k, None)

def load_env(env_path: str):
    p = Path(env_path)
    if not p.exists():
        raise FileNotFoundError(f"Missing env file: {env_path}")
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()

@dataclass
class IBConnCfg:
    mode: str
    host: str
    port: int
    client_id: int
    expected_acct: str

def load_cfg() -> IBConnCfg:
    mode = os.getenv("IB_MODE", "").strip().upper()
    host = os.getenv("IB_HOST", "127.0.0.1").strip()
    port = int(os.getenv("IB_PORT", "0"))
    client_id = int(os.getenv("IB_CLIENT_ID", "0"))
    expected_acct = {"LIVE": "U17861226", "PAPER": "DUP148773"}.get(mode, "")

    if mode not in ("LIVE", "PAPER"):
        raise SystemExit(f"IB_MODE invalid: {mode!r} (must be LIVE or PAPER)")
    if port <= 0 or client_id <= 0:
        raise SystemExit(f"IB_PORT / IB_CLIENT_ID missing or invalid (port={port}, client_id={client_id})")
    if not expected_acct:
        raise SystemExit(f"Expected account not set for mode={mode}")

    return IBConnCfg(mode, host, port, client_id, expected_acct)

def connect_checked(timeout: int = 8) -> tuple[IB, IBConnCfg, str]:
    cfg = load_cfg()
    ib = IB()
    ib.connect(cfg.host, cfg.port, clientId=cfg.client_id, timeout=timeout)

    accts = ib.managedAccounts()
    if not accts:
        ib.disconnect()
        raise SystemExit("Connected but managedAccounts() is empty")

    acct = accts[0]
    if acct != cfg.expected_acct:
        ib.disconnect()
        raise SystemExit(
            "SAFETY BLOCK ✅\n"
            f"Connected account mismatch!\n"
            f"  mode={cfg.mode}\n"
            f"  expected={cfg.expected_acct}\n"
            f"  got={acct}\n"
            f"  host={cfg.host} port={cfg.port} clientId={cfg.client_id}"
        )

    return ib, cfg, acct

def connect_from_envfile(env_path: str, timeout: int = 8) -> tuple[IB, IBConnCfg, str]:
    clear_env_keys()
    load_env(env_path)
    return connect_checked(timeout=timeout)
