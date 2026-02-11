#!/usr/bin/env python3
"""
Fetch IBKR symbol profile (industry/category/subcategory/longName) via ContractDetails
and cache it to: data/reference/ibkr_symbol_profile.csv

Usage examples:
  # 1) From a specific daily DIX details CSV (recommended)
  python scripts/fetch_ibkr_symbol_profile.py --details_csv data/dix/details/diy_dix_details_20260114_ibkr.csv

  # 2) Or from an explicit symbols list file (one symbol per line)
  python scripts/fetch_ibkr_symbol_profile.py --symbols_file data/reference/symbols.txt

  # 3) Connect params (match your gateway)
  python scripts/fetch_ibkr_symbol_profile.py --host 127.0.0.1 --port 4002 --clientId 26
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ib_insync import IB, Stock  # type: ignore


OUT_CSV = Path("data/reference/ibkr_symbol_profile.csv")


def ensure_parent(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)


def read_symbols_from_details(details_csv: Path) -> List[str]:
    if not details_csv.exists():
        raise FileNotFoundError(f"details_csv not found: {details_csv}")
    with details_csv.open("r", newline="") as f:
        reader = csv.DictReader(f)
        if "Symbol" not in (reader.fieldnames or []):
            raise ValueError(f"'Symbol' column not found in {details_csv}")
        syms = []
        for row in reader:
            s = (row.get("Symbol") or "").strip()
            if s:
                syms.append(s)
    # de-dup preserve order
    seen: Set[str] = set()
    out: List[str] = []
    for s in syms:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def read_symbols_from_file(symbols_file: Path) -> List[str]:
    if not symbols_file.exists():
        raise FileNotFoundError(f"symbols_file not found: {symbols_file}")
    syms = []
    for line in symbols_file.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            syms.append(s)
    # de-dup preserve order
    seen: Set[str] = set()
    out: List[str] = []
    for s in syms:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def load_existing_cache(path: Path) -> Dict[str, Dict[str, str]]:
    """
    Returns dict: symbol -> rowdict
    """
    if not path.exists():
        return {}
    rows: Dict[str, Dict[str, str]] = {}
    with path.open("r", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            sym = (r.get("symbol") or "").strip()
            if sym:
                rows[sym] = {k: (v or "") for k, v in r.items()}
    return rows


def normalize_for_ibkr(symbol: str) -> str:
    """
    IBKR often wants class shares like BRK B, BF B instead of BRK.B / BF.B.
    We keep original symbol in output but query with normalized.
    """
    s = symbol.strip().upper()
    if "." in s:
        # BRK.B -> BRK B
        s = s.replace(".", " ")
    return s


def fetch_profile_one(ib: IB, symbol: str, currency: str = "USD") -> Optional[Dict[str, str]]:
    qsym = normalize_for_ibkr(symbol)
    contract = Stock(qsym, "SMART", currency)

    cds = ib.reqContractDetails(contract)
    if not cds:
        return None

    cd = cds[0]
    sec = cd.secIdList or []
    _ = sec  # placeholder (kept for future use)

    industry = getattr(cd, "industry", "") or ""
    category = getattr(cd, "category", "") or ""
    subcategory = getattr(cd, "subcategory", "") or ""

    long_name = ""
    if getattr(cd, "longName", None):
        long_name = cd.longName or ""
    elif getattr(cd.contract, "localSymbol", None):
        long_name = cd.contract.localSymbol or ""

    exchange = getattr(cd.contract, "exchange", "") or ""
    primary_exch = getattr(cd.contract, "primaryExchange", "") or ""

    return {
        "symbol": symbol,
        "query_symbol": qsym,
        "industry": industry,
        "category": category,
        "subcategory": subcategory,
        "longName": long_name,
        "exchange": exchange,
        "primaryExchange": primary_exch,
    }


def write_cache(path: Path, rows: Dict[str, Dict[str, str]]) -> None:
    ensure_parent(path)
    fieldnames = [
        "symbol",
        "query_symbol",
        "industry",
        "category",
        "subcategory",
        "longName",
        "exchange",
        "primaryExchange",
    ]
    # stable order by symbol
    keys = sorted(rows.keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for k in keys:
            r = rows[k]
            w.writerow({fn: r.get(fn, "") for fn in fieldnames})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--details_csv", default=None, help="Daily DIX details CSV with Symbol column")
    ap.add_argument("--symbols_file", default=None, help="Text file with 1 symbol per line")
    ap.add_argument("--out", default=str(OUT_CSV), help="Output cache CSV path")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4002)
    ap.add_argument("--clientId", type=int, default=26, help="Use a unique clientId (do not reuse 21/22)")
    ap.add_argument("--sleep", type=float, default=0.03, help="Sleep between IBKR requests (seconds)")
    ap.add_argument("--limit", type=int, default=0, help="For testing: only fetch first N symbols (0=all)")
    args = ap.parse_args()

    if (args.details_csv is None) == (args.symbols_file is None):
        print("ERROR: Provide exactly one of --details_csv OR --symbols_file", file=sys.stderr)
        return 2

    out_path = Path(args.out)

    # Load symbols
    if args.details_csv:
        syms = read_symbols_from_details(Path(args.details_csv))
    else:
        syms = read_symbols_from_file(Path(args.symbols_file))

    if args.limit and args.limit > 0:
        syms = syms[: args.limit]

    # Load existing cache and skip already-known
    cache = load_existing_cache(out_path)
    todo = [s for s in syms if s not in cache]

    print(f"Symbols input: {len(syms)}")
    print(f"Cache exists: {len(cache)}")
    print(f"To fetch now: {len(todo)}")
    if not todo:
        print("Nothing to do.")
        return 0

    ib = IB()
    print(f"Connecting IBKR {args.host}:{args.port} clientId={args.clientId} ...")
    ib.connect(args.host, args.port, clientId=args.clientId, timeout=10)

    try:
        missing = 0
        fetched = 0
        for i, sym in enumerate(todo, 1):
            prof = fetch_profile_one(ib, sym, currency="USD")
            if prof is None:
                missing += 1
                cache[sym] = {
                    "symbol": sym,
                    "query_symbol": normalize_for_ibkr(sym),
                    "industry": "",
                    "category": "",
                    "subcategory": "",
                    "longName": "",
                    "exchange": "",
                    "primaryExchange": "",
                }
            else:
                cache[sym] = prof
                fetched += 1

            if i % 25 == 0 or i == len(todo):
                print(f"  progress {i}/{len(todo)} | fetched={fetched} missing={missing}")
                write_cache(out_path, cache)

            time.sleep(args.sleep)

        print(f"Saved cache: {out_path}  (total rows={len(cache)})")
        return 0
    finally:
        ib.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
