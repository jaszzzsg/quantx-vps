#!/usr/bin/env python3
"""
Check if unnamed sector is in top 5 after weekly report.
Run this after each weekly report to monitor sector classification health.

Usage:
    python scripts/tools/check_unnamed_sector.py

Returns exit code 1 if unnamed is in top 5 (action needed).
"""
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

def main():
    # Load classification files
    etf_master = pd.read_csv(ROOT / "data" / "etf_classification_master.csv")
    profile_cache = pd.read_csv(ROOT / "data" / "ibkr_symbol_profile_cache.csv")

    etf_tickers = set(etf_master['ticker'].dropna().str.upper())
    profile_tickers = set(profile_cache['symbol'].dropna().str.upper())
    classified = etf_tickers | profile_tickers

    # Find latest daily details
    details_dir = ROOT / "data" / "dix" / "details"
    files = sorted(details_dir.glob("diy_dix_details_*_ibkr.csv"))
    if not files:
        print("ERROR: No daily details files found")
        return 1

    latest = files[-1]
    print(f"Checking: {latest.name}")

    details = pd.read_csv(latest)
    details['symbol_upper'] = details['Symbol'].str.upper()
    details['is_classified'] = details['symbol_upper'].isin(classified)

    def get_sector(row):
        sym = row['symbol_upper']
        if sym in etf_tickers:
            match = etf_master[etf_master['ticker'].str.upper() == sym]
            if len(match): return match.iloc[0]['sector']
        if sym in profile_tickers:
            match = profile_cache[profile_cache['symbol'].str.upper() == sym]
            if len(match): return match.iloc[0].get('industry', 'Unknown')
        return 'Unnamed'

    details['sector'] = details.apply(get_sector, axis=1)

    # Aggregate
    by_sector = details.groupby('sector').agg(
        short_dollars=('short_dollars', 'sum'),
        count=('Symbol', 'count')
    ).sort_values('short_dollars', ascending=False)

    print("\n=== TOP 10 SECTORS ===")
    for i, (sector, row) in enumerate(by_sector.head(10).iterrows(), 1):
        print(f"{i:2d}. {sector:30s}: ${row['short_dollars']/1e9:.2f}B ({row['count']} names)")

    top5 = list(by_sector.head(5).index)
    if 'Unnamed' in top5:
        pos = top5.index('Unnamed') + 1
        print(f"\n❌ ACTION NEEDED: Unnamed is at position {pos}")
        print("   Run sector classification to reduce unnamed sector")

        # Show top 20 unnamed
        unnamed = details[details['sector'] == 'Unnamed'].sort_values('short_dollars', ascending=False)
        print("\n=== TOP 20 UNNAMED TICKERS ===")
        for i, (_, row) in enumerate(unnamed.head(20).iterrows(), 1):
            print(f"{i:2d}. {row['Symbol']:8s}: ${row['short_dollars']/1e9:.3f}B")

        return 1
    else:
        unnamed_pos = list(by_sector.index).index('Unnamed') + 1
        print(f"\n✅ OK: Unnamed is at position {unnamed_pos} (out of top 5)")
        return 0

if __name__ == "__main__":
    sys.exit(main())
