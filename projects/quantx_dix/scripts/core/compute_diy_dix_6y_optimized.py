from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from ib_insync import IB, Stock, Contract, util

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from utils.ibkr_client_id import get_client_id, release_client_id

HISTORY_DIR = PROJECT_ROOT / "data" / "dix" / "history"
LOGS_DIR = PROJECT_ROOT / "logs"
FINRA_CACHE_DIR = PROJECT_ROOT / "data" / "finra_cache" / "short_volume"
INVALID_SYMS_PATH = PROJECT_ROOT / "data" / "ibkr_invalid_symbols.json"
CONTRACT_CACHE_PATH = PROJECT_ROOT / "data" / "ibkr_contract_cache.json"

HISTORY_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
FINRA_CACHE_DIR.mkdir(parents=True, exist_ok=True)

FINRA_URLS = [
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt",
    "https://cdn.finra.org/equity/regsho/daily/NMSshvol{ymd}.txt",
]

SYM_RE = re.compile(r"^[A-Z]{1,6}$")

def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def pct(a: int, b: int) -> int:
    return 0 if b <= 0 else int(round((a / b) * 100))

def daterange(start_ymd: str, end_ymd: str, skip_weekends: bool = True) -> List[str]:
    s = datetime.strptime(start_ymd, "%Y%m%d").date()
    e = datetime.strptime(end_ymd, "%Y%m%d").date()
    out = []
    d = s
    while d <= e:
        if not skip_weekends or d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out

def load_invalid_syms() -> set[str]:
    if INVALID_SYMS_PATH.exists():
        try:
            return set(json.loads(INVALID_SYMS_PATH.read_text()).get("symbols", []))
        except Exception:
            return set()
    return set()

def save_invalid_syms(syms: set[str]) -> None:
    INVALID_SYMS_PATH.write_text(json.dumps({"symbols": sorted(syms)}, indent=2))

def load_contract_cache() -> Dict[str, dict]:
    if CONTRACT_CACHE_PATH.exists():
        try:
            return json.loads(CONTRACT_CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}

def save_contract_cache(cache: Dict[str, dict]) -> None:
    CONTRACT_CACHE_PATH.write_text(json.dumps(cache, indent=2, sort_keys=True))

def download_finra_file(ymd: str, timeout: int = 25) -> Optional[Path]:
    cached_txt = FINRA_CACHE_DIR / f"finra_shvol_{ymd}.txt"
    if cached_txt.exists() and cached_txt.stat().st_size > 1000:
        return cached_txt

    sess = requests.Session()
    for url_tmpl in FINRA_URLS:
        url = url_tmpl.format(ymd=ymd)
        try:
            r = sess.get(url, timeout=timeout)
            if r.status_code != 200 or not r.content:
                continue
            cached_txt.write_bytes(r.content)
            return cached_txt
        except Exception:
            continue
    return None

def parse_finra_short_volume(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep="|", header=None, dtype=str, engine="python")
    first = df.iloc[0].tolist()
    if any(str(x).lower() in ("symbol", "shortvolume", "totalvolume") for x in first):
        df = pd.read_csv(path, sep="|", header=0, dtype=str, engine="python")
    else:
        if df.shape[1] < 5:
            raise ValueError(f"Unexpected format")
        df = df.iloc[:, :5]
        df.columns = ["Symbol", "ShortVolume", "ShortExemptVolume", "TotalVolume", "Market"]

    for c in ["ShortVolume", "ShortExemptVolume", "TotalVolume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["Symbol"] = df["Symbol"].astype(str).str.strip()
    return df.dropna(subset=["Symbol", "TotalVolume"])

def build_day_universe_from_finra(ymd: str, top_n: int, min_total_vol: int, cache_universe: bool) -> Tuple[List[str], str]:
    uni_cache = FINRA_CACHE_DIR / f"universe_{ymd}_top{top_n}_min{min_total_vol}.json"
    if cache_universe and uni_cache.exists():
        data = json.loads(uni_cache.read_text())
        return data["symbols"], f"cache:{uni_cache.name}"

    finra_path = download_finra_file(ymd)
    if finra_path is None:
        return [], "finra:not_found"

    df = parse_finra_short_volume(finra_path)
    df = df[df["Symbol"].apply(lambda s: bool(SYM_RE.match(str(s))))]

    if min_total_vol > 0:
        df = df[df["TotalVolume"] >= min_total_vol]

    df = df.sort_values("TotalVolume", ascending=False)
    if top_n and top_n > 0:
        df = df.head(top_n)

    symbols = df["Symbol"].astype(str).tolist()

    if cache_universe:
        uni_cache.write_text(json.dumps({"ymd": ymd, "symbols": symbols}, indent=2))

    return symbols, f"finra:{finra_path.name}"

def connect_ib_with_retry(host: str, port: int, client_id: int, timeout: int = 10, max_tries: int = 5) -> Tuple[IB, int]:
    """Connect, accepting account data timeouts (harmless)."""
    for k in range(max_tries):
        cid = client_id + k
        ib = IB()
        try:
            print(f"[IBKR] Attempt {k+1}/{max_tries}: Connecting clientId={cid}...", flush=True)
            ib.connect(host, port, clientId=cid)
            print(f"[IBKR] ✓ Connected!", flush=True)
            return ib, cid
        except Exception as e:
            # If connected despite exception, use it
            try:
                if ib.isConnected():
                    print(f"[IBKR] Connected (account data timeout ignored)", flush=True)
                    return ib, cid
            except:
                pass
            print(f"[IBKR] ✗ {e}", flush=True)
            try:
                ib.disconnect()
            except:
                pass
            time.sleep(1)

    raise RuntimeError(f"Could not connect after {max_tries} attempts")

def get_qualified_contract(ib: IB, sym: str, contract_cache: Dict[str, dict], invalid: set[str]) -> Optional[Contract]:
    if sym in invalid:
        return None

    cached = contract_cache.get(sym)
    if cached and cached.get("conId"):
        c = Stock(sym, cached.get("exchange", "SMART"), cached.get("currency", "USD"))
        c.conId = int(cached["conId"])
        c.primaryExchange = cached.get("primaryExchange", "")
        return c

    try:
        c0 = Stock(sym, "SMART", "USD")
        res = ib.qualifyContracts(c0)
        if not res:
            invalid.add(sym)
            save_invalid_syms(invalid)
            return None
        qc = res[0]
        contract_cache[sym] = {
            "conId": int(qc.conId),
            "exchange": getattr(qc, "exchange", "SMART") or "SMART",
            "primaryExchange": getattr(qc, "primaryExchange", "") or "",
            "currency": getattr(qc, "currency", "USD") or "USD",
        }
        save_contract_cache(contract_cache)
        return qc
    except Exception:
        invalid.add(sym)
        save_invalid_syms(invalid)
        return None

def check_connection_health(ib: IB) -> bool:
    """Check if IBKR connection is still alive and healthy."""
    try:
        if not ib.isConnected():
            return False
        # Try a simple API call to verify connection works
        ib.reqCurrentTime()
        return True
    except Exception:
        return False

def req_close_for_day(ib: IB, contract: Contract, ymd: str, sleep_s: float) -> Optional[float]:
    try:
        bars = ib.reqHistoricalData(contract, endDateTime=f"{ymd} 23:59:59", durationStr="1 D", barSizeSetting="1 day", whatToShow="TRADES", useRTH=False, formatDate=1)
        if sleep_s > 0:
            time.sleep(sleep_s)
        if not bars:
            return None
        return float(bars[-1].close)
    except Exception as e:
        # Check if this is a connection error
        error_str = str(e).lower()
        if any(x in error_str for x in ['connectivity', 'connection', 'peer closed', 'error 1100']):
            print(f"\n[WARN] Connection error detected: {e}", flush=True)
            raise  # Re-raise to trigger reconnection
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--clientId", type=int, default=0, help="Base clientId (0=auto-assign)")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--sleep", type=float, default=0.02)
    ap.add_argument("--top_n", type=int, default=1200)
    ap.add_argument("--min_total_vol", type=int, default=200000)
    ap.add_argument("--out", required=True, help="Output file path")
    args = ap.parse_args()

    dates = daterange(args.start, args.end, skip_weekends=True)
    n_days = len(dates)

    out_path = Path(args.out)
    log_path = LOGS_DIR / f"chunk_{args.start}_{args.end}_{now_ts()}.log"

    invalid = load_invalid_syms()
    contract_cache = load_contract_cache()

    print(f"[CHUNK] {args.start} → {args.end} ({n_days} days)", flush=True)
    print(f"[OUT] {out_path}", flush=True)

    # ── DATA QUALITY GUARD ────────────────────────────────────────────────────
    # If the output file already exists with meaningful data, refuse to overwrite.
    # Rule: file must have fewer than 500 data rows OR close-price coverage < 50%
    # to be considered safe to overwrite (empty/junk).  Any file with good data
    # is PROTECTED — operator must delete it manually before re-running.
    if out_path.exists():
        try:
            import csv as _csv
            with open(out_path, newline="") as _f:
                _rows = list(_csv.DictReader(_f))
            _total = len(_rows)
            _with_close = sum(1 for r in _rows if r.get("close", "").strip())
            _coverage = (_with_close / _total * 100) if _total else 0
            _dates_found = sorted(set(r.get("ymd","") for r in _rows if r.get("ymd","")))
            _first = _dates_found[0] if _dates_found else "?"
            _last  = _dates_found[-1] if _dates_found else "?"
            print(f"[GUARD] Existing file: {_total:,} rows | close coverage: {_coverage:.1f}% | dates: {_first}→{_last}", flush=True)
            if _total >= 500 and _coverage >= 50.0:
                print(f"[GUARD] ❌ ABORT — file contains good-quality data ({_total:,} rows, {_coverage:.1f}% close coverage).", flush=True)
                print(f"[GUARD]    Delete {out_path} manually if you truly want to overwrite.", flush=True)
                raise SystemExit(1)
            else:
                print(f"[GUARD] ⚠️  File exists but is low-quality/empty ({_total} rows, {_coverage:.1f}% coverage) — safe to overwrite.", flush=True)
        except SystemExit:
            raise
        except Exception as _ge:
            print(f"[GUARD] Could not read existing file ({_ge}), proceeding with overwrite.", flush=True)
    # ─────────────────────────────────────────────────────────────────────────

    # Get client ID (auto or manual)
    if args.clientId == 0:
        client_id = get_client_id(args.host, args.port, f"chunk_{args.start}_{args.end}")
    else:
        client_id = args.clientId
        print(f"[ClientID] Using manual ID {client_id}")

    print(f"[IBKR] Connecting to {args.host}:{args.port}...", flush=True)

    with open(log_path, "w") as lf:
        lf.write(f"start={args.start} end={args.end} days={n_days}\n")

    ib, _cid = connect_ib_with_retry(args.host, args.port, client_id)
    print(f"[IBKR] Active clientId={_cid}", flush=True)

    try:
        with open(out_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ymd", "symbol", "close", "finra_source", "universe_n", "missing_n"])

            start_time = time.time()
            consecutive_failures = 0
            last_connection_check = time.time()

            for di, ymd in enumerate(dates, start=1):
                # Check connection health every 10 minutes or if we have many consecutive failures
                if (time.time() - last_connection_check > 600) or consecutive_failures > 20:
                    if not check_connection_health(ib):
                        print(f"\n[WARN] Connection lost! Reconnecting...", flush=True)
                        try:
                            ib.disconnect()
                        except Exception:
                            pass
                        ib, _cid = connect_ib_with_retry(args.host, args.port, client_id)
                        print(f"[IBKR] ✓ Reconnected with clientId={_cid}", flush=True)
                        consecutive_failures = 0
                    last_connection_check = time.time()

                symbols, src = build_day_universe_from_finra(ymd, args.top_n, args.min_total_vol, True)
                symbols = [s for s in symbols if s not in invalid]
                n_syms = len(symbols)

                elapsed = time.time() - start_time
                speed = di / (elapsed / 3600) if elapsed > 0 else 0
                eta_hours = (n_days - di) / speed if speed > 0 else 0

                print(f"[{pct(di, n_days):>3}%] Day {di}/{n_days} {ymd} | {n_syms} syms | {speed:.1f} d/hr | ETA: {eta_hours:.1f}h", flush=True)

                if n_syms == 0:
                    w.writerow([ymd, "", "", src, 0, 0])
                    continue

                missing = 0
                day_successful_fetches = 0
                for si, sym in enumerate(symbols, start=1):
                    if si % 100 == 0:
                        print(f"   [{pct(si, n_syms):>3}%] {si}/{n_syms}", end="\r", flush=True)

                    try:
                        qc = get_qualified_contract(ib, sym, contract_cache, invalid)
                        if qc is None:
                            missing += 1
                            w.writerow([ymd, sym, "", src, n_syms, missing])
                            continue

                        c = req_close_for_day(ib, qc, ymd, args.sleep)
                        if c is None:
                            missing += 1
                            consecutive_failures += 1
                        else:
                            day_successful_fetches += 1
                            consecutive_failures = 0  # Reset on success
                        w.writerow([ymd, sym, "" if c is None else f"{c:.6f}", src, n_syms, missing])
                    except Exception as e:
                        # Connection error detected, try to reconnect
                        print(f"\n[ERROR] {e}", flush=True)
                        print(f"[WARN] Attempting reconnection...", flush=True)
                        try:
                            ib.disconnect()
                        except Exception:
                            pass
                        ib, _cid = connect_ib_with_retry(args.host, args.port, client_id)
                        print(f"[IBKR] ✓ Reconnected with clientId={_cid}", flush=True)
                        consecutive_failures = 0
                        last_connection_check = time.time()
                        # Write this symbol as missing after reconnection
                        missing += 1
                        w.writerow([ymd, sym, "", src, n_syms, missing])

                # Safety check: if we got 0 closes for a day with >100 symbols, something is wrong
                if n_syms > 100 and day_successful_fetches == 0:
                    print(f"\n[CRITICAL] Got 0 closes for day with {n_syms} symbols - connection may be broken!", flush=True)
                    if not check_connection_health(ib):
                        print(f"[WARN] Connection confirmed broken. Reconnecting...", flush=True)
                        try:
                            ib.disconnect()
                        except Exception:
                            pass
                        ib, _cid = connect_ib_with_retry(args.host, args.port, client_id)
                        print(f"[IBKR] ✓ Reconnected with clientId={_cid}", flush=True)
                        consecutive_failures = 0
                        last_connection_check = time.time()

                print(f"\n   ✓ {n_syms - missing} closes, {missing} missing", flush=True)
    finally:
        ib.disconnect()
        if args.clientId == 0:
            release_client_id(_cid)
    
    print(f"\n[100%] DONE! Saved: {out_path}", flush=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[FATAL ERROR] {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        traceback.print_exc()
        sys.exit(1)
