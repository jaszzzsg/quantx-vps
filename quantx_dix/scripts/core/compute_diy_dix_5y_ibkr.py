from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from ib_insync import IB, Stock, Contract, util
import logging

util.logToConsole(logging.CRITICAL)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt.gz",
    "https://cdn.finra.org/equity/regsho/daily/NMSshvol{ymd}.txt.gz",
]

SYM_RE = re.compile(r"^[A-Z]{1,6}$")


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def pct(a: int, b: int) -> int:
    return 0 if b <= 0 else int(round((a / b) * 100))


def daterange(start_ymd: str, end_ymd: str) -> List[str]:
    s = datetime.strptime(start_ymd, "%Y%m%d").date()
    e = datetime.strptime(end_ymd, "%Y%m%d").date()
    out = []
    d = s
    while d <= e:
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
    cached_gz = FINRA_CACHE_DIR / f"finra_shvol_{ymd}.txt.gz"

    if cached_txt.exists() and cached_txt.stat().st_size > 1000:
        return cached_txt
    if cached_gz.exists() and cached_gz.stat().st_size > 1000:
        return cached_gz

    sess = requests.Session()
    for url_tmpl in FINRA_URLS:
        url = url_tmpl.format(ymd=ymd)
        try:
            r = sess.get(url, timeout=timeout)
            if r.status_code != 200 or not r.content:
                continue
            if url.endswith(".gz"):
                cached_gz.write_bytes(r.content)
                return cached_gz
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
            raise ValueError(f"Unexpected FINRA format cols={df.shape[1]}")
        df = df.iloc[:, :5]
        df.columns = ["Symbol", "ShortVolume", "ShortExemptVolume", "TotalVolume", "Market"]

    for c in ["ShortVolume", "ShortExemptVolume", "TotalVolume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["Symbol"] = df["Symbol"].astype(str).str.strip()
    if "Market" in df.columns:
        df["Market"] = df["Market"].astype(str).str.strip()

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

    if "Market" in df.columns:
        m = df["Market"].str.upper()
        df = df[~m.str.contains("OTC", na=False)]
        df = df[~m.str.contains("PINK", na=False)]

    if min_total_vol > 0:
        df = df[df["TotalVolume"] >= min_total_vol]

    df = df.sort_values("TotalVolume", ascending=False)
    if top_n and top_n > 0:
        df = df.head(top_n)

    symbols = df["Symbol"].astype(str).tolist()

    if cache_universe:
        uni_cache.write_text(json.dumps({"ymd": ymd, "symbols": symbols}, indent=2))

    return symbols, f"finra:{finra_path.name}"


def connect_ib_with_retry(host: str, port: int, client_id: int, timeout: int = 10, max_tries: int = 20) -> Tuple[IB, int]:
    last_exc = None
    for k in range(max_tries):
        cid = client_id + k
        ib = IB()
        try:
            ib.connect(host, port, clientId=cid, timeout=timeout)
            if k > 0:
                print(f"[IBKR] Connected with clientId={cid}")
            return ib, cid
        except Exception as e:
            last_exc = e
            try:
                ib.disconnect()
            except Exception:
                pass
            time.sleep(0.4)
    raise RuntimeError(f"IBKR connect failed after {max_tries} tries. Last error: {last_exc}")


def get_qualified_contract(ib: IB, sym: str, contract_cache: Dict[str, dict], invalid: set[str], log_path: Path) -> Optional[Contract]:
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


def req_close_for_day(ib: IB, contract: Contract, ymd: str, sleep_s: float) -> Optional[float]:
    try:
        bars = ib.reqHistoricalData(contract, endDateTime=f"{ymd} 23:59:59", durationStr="1 D", barSizeSetting="1 day", whatToShow="TRADES", useRTH=False, formatDate=1)
        if sleep_s > 0:
            time.sleep(sleep_s)
        if not bars:
            return None
        return float(bars[-1].close)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--clientId", type=int, default=25)
    ap.add_argument("--years", type=int, default=6)
    ap.add_argument("--start", default="")
    ap.add_argument("--end", default="")
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--top_n", type=int, default=1200)
    ap.add_argument("--min_total_vol", type=int, default=200000)
    ap.add_argument("--cache_finra", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    if args.end:
        end_ymd = args.end
    else:
        end_ymd = (datetime.now(timezone.utc).date() - timedelta(days=1)).strftime("%Y%m%d")

    if args.start:
        start_ymd = args.start
    else:
        start_ymd = (datetime.strptime(end_ymd, "%Y%m%d").date() - timedelta(days=int(args.years * 365.25))).strftime("%Y%m%d")

    dates = daterange(start_ymd, end_ymd)
    n_days = len(dates)

    out_path = Path(args.out) if args.out else (HISTORY_DIR / f"diy_dix_history_{args.years}y_{start_ymd}-{end_ymd}_finraTop{args.top_n}_minVol{args.min_total_vol}.csv")
    log_path = LOGS_DIR / f"dix_history_{args.years}y_{now_ts()}.log"

    invalid = load_invalid_syms()
    contract_cache = load_contract_cache()

    print(f"[INIT] start={start_ymd} end={end_ymd} days={n_days}")
    print(f"[INIT] FINRA: top_n={args.top_n} min_vol={args.min_total_vol}")
    print(f"[INIT] IBKR: {args.host}:{args.port} clientId={args.clientId}")
    print(f"[INIT] Output: {out_path}")

    with open(log_path, "w") as lf:
        lf.write(f"start={start_ymd} end={end_ymd} days={n_days}\n")

    ib, _cid = connect_ib_with_retry(args.host, args.port, args.clientId)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as f:
        csv.writer(f).writerow(["ymd", "symbol", "close", "finra_source", "universe_n", "missing_n"])

    for di, ymd in enumerate(dates, start=1):
        day_pct = pct(di, n_days)
        symbols, src = build_day_universe_from_finra(ymd, args.top_n, args.min_total_vol, args.cache_finra)
        symbols = [s for s in symbols if s not in invalid]
        n_syms = len(symbols)

        print(f"\n[{day_pct:>3}%] Day {di}/{n_days} ymd={ymd} | symbols={n_syms}")

        if n_syms == 0:
            with open(out_path, "a", newline="") as f:
                csv.writer(f).writerow([ymd, "", "", src, 0, 0])
            continue

        missing = 0
        with open(out_path, "a", newline="") as f:
            w = csv.writer(f)
            for si, sym in enumerate(symbols, start=1):
                if si == 1 or si % 50 == 0 or si == n_syms:
                    print(f"   [{pct(si, n_syms):>3}%] ticker {si}/{n_syms}", end="\r", flush=True)

                qc = get_qualified_contract(ib, sym, contract_cache, invalid, log_path)
                if qc is None:
                    missing += 1
                    w.writerow([ymd, sym, "", src, n_syms, missing])
                    continue

                c = req_close_for_day(ib, qc, ymd, args.sleep)
                if c is None:
                    missing += 1
                w.writerow([ymd, sym, "" if c is None else f"{c:.6f}", src, n_syms, missing])

        print(f"\n   Completed: {n_syms - missing} closes, {missing} missing")

    ib.disconnect()
    print(f"\n[100%] DONE! Output: {out_path}")


if __name__ == "__main__":
    main()
