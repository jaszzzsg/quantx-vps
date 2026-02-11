#!/usr/bin/env python3
"""
check_last_date_quality.py

Run before resuming any DIX chunk fetch that died mid-run.
Checks the LAST date in the file for close price coverage and recommends
whether to start from that date (retry) or the next trading day (skip).

Usage:
    python scripts/tools/check_last_date_quality.py data/dix/history/chunk_2021.csv
"""

import sys
import csv
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict


def next_trading_day(ymd: str) -> str:
    """Return the next weekday after ymd (YYYYMMDD), skipping Sat/Sun."""
    d = datetime.strptime(ymd, "%Y%m%d")
    d += timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d.strftime("%Y%m%d")


def main():
    if len(sys.argv) < 2:
        print("Usage: python check_last_date_quality.py <csv_file>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    # Read all rows
    by_date = defaultdict(list)
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            ymd = row.get("ymd", "").strip()
            if ymd:
                by_date[ymd].append(row)

    if not by_date:
        print("File is empty or has no data rows.")
        sys.exit(1)

    all_dates = sorted(by_date.keys())
    total_dates = len(all_dates)
    first_date = all_dates[0]
    last_date  = all_dates[-1]

    # Overall file stats
    all_rows = [r for rows in by_date.values() for r in rows]
    total_rows = len(all_rows)
    total_with_close = sum(1 for r in all_rows if r.get("close", "").strip())
    overall_pct = total_with_close / total_rows * 100 if total_rows else 0

    print("=" * 60)
    print(f"File      : {path}")
    print(f"Dates     : {first_date} → {last_date}  ({total_dates} trading days)")
    print(f"Total rows: {total_rows:,}  |  Close coverage: {overall_pct:.1f}%")
    print("=" * 60)

    # Per-date breakdown for last 5 dates
    print("\nLast 5 dates coverage:")
    for ymd in all_dates[-5:]:
        rows = by_date[ymd]
        n = len(rows)
        w = sum(1 for r in rows if r.get("close", "").strip())
        pct = w / n * 100 if n else 0
        flag = "✅" if pct >= 80 else "⚠️ LOW" if pct >= 50 else "❌ BAD"
        print(f"  {ymd}  {n:4d} rows  {pct:5.1f}% close  {flag}")

    # Decision for the LAST date
    last_rows = by_date[last_date]
    last_n = len(last_rows)
    last_w = sum(1 for r in last_rows if r.get("close", "").strip())
    last_pct = last_w / last_n * 100 if last_n else 0
    next_day = next_trading_day(last_date)

    print("\n" + "=" * 60)
    print(f"LAST DATE: {last_date}  →  {last_n} rows, {last_pct:.1f}% close coverage")

    if last_pct >= 80:
        print(f"  ✅ GOOD quality — last date is complete.")
        print(f"  ▶  Recommended: start new fetch from NEXT day: {next_day}")
        print(f"     --start {next_day} --end <end_date> --out chunk_<YYYY>_part2_{next_day}_<end>.csv")
    elif last_pct >= 50:
        print(f"  ⚠️  PARTIAL quality — last date may be incomplete.")
        print(f"  ▶  Option A (retry last day): --start {last_date} (re-fetch, saves to new part file)")
        print(f"  ▶  Option B (skip last day) : --start {next_day}")
        print(f"  ⚑  Please confirm which option to use.")
    else:
        print(f"  ❌ BAD quality — last date has very few close prices.")
        print(f"  ▶  Recommended: start new fetch from SAME day: {last_date}")
        print(f"     --start {last_date} --end <end_date> --out chunk_<YYYY>_part2_{last_date}_<end>.csv")

    print("=" * 60)
    print(f"\nNOTE: Always save the resumed fetch to a NEW part file.")
    print(f"  e.g.  chunk_2021_part2_{next_day}_20211231.csv")
    print(f"  Then merge parts once all complete and coverage verified.")


if __name__ == "__main__":
    main()
