from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DETAILS_DIR = ROOT / "data" / "dix" / "details"
HISTORY_DIR = ROOT / "data" / "dix" / "history"

ENRICHED_GLOB = "diy_dix_history_6y_*_enriched.csv"


def newest_enriched_master() -> Path:
    files = sorted(HISTORY_DIR.glob(ENRICHED_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No enriched master found in {HISTORY_DIR} matching {ENRICHED_GLOB}")
    return files[0]


def list_daily_files(back_days: int) -> List[Path]:
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=back_days)).strftime("%Y%m%d")
    out = []
    for p in sorted(DETAILS_DIR.glob("diy_dix_details_*_ibkr.csv")):
        name = p.name
        ymd = name.split("_")[3] if len(name.split("_")) >= 4 else ""
        if ymd.isdigit() and ymd >= cutoff:
            out.append(p)
    return out


def load_daily_details(paths: List[Path]) -> pd.DataFrame:
    frames = []
    for p in paths:
        ymd = p.name.split("_")[3]
        df = pd.read_csv(p)
        df["ymd"] = str(ymd)
        df["Symbol"] = df["Symbol"].astype(str).str.strip().str.upper()
        
        # Ensure all critical columns are numeric
        for c in ["ShortVolume", "ShortExemptVolume", "TotalVolume", "close", "short_dollars", "total_dollars"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        
        frames.append(df)
    
    if not frames:
        return pd.DataFrame()
    
    ddf = pd.concat(frames, ignore_index=True)
    return ddf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--back-days", type=int, default=60, help="How many calendar days back to look for daily detail files")
    ap.add_argument("--out", type=str, default="", help="Optional output path; default overwrites the current enriched master")
    args = ap.parse_args()

    master_path = newest_enriched_master()
    print(f"[INFO] Enriched master: {master_path}")

    daily_files = list_daily_files(args.back_days)
    print(f"[INFO] Daily detail files found (>= last {args.back_days} days): {len(daily_files)}")
    for p in daily_files[-10:]:
        print(f"  - {p.name}")

    if not daily_files:
        print("[WARN] No daily detail files found. Nothing to merge. Exiting.")
        return

    ddf = load_daily_details(daily_files)
    if ddf.empty:
        print("[WARN] Daily details loaded empty. Exiting.")
        return

    # Load master
    m = pd.read_csv(master_path)
    m["ymd"] = m["ymd"].astype(str)
    m["symbol"] = m["symbol"].astype(str).str.strip().str.upper()

    # Build rows with ALL critical columns from daily details
    base = pd.DataFrame({
        "ymd": ddf["ymd"].astype(str),
        "symbol": ddf["Symbol"].astype(str),
        "close": pd.to_numeric(ddf.get("close"), errors="coerce"),
        "ShortVolume": pd.to_numeric(ddf.get("ShortVolume"), errors="coerce"),
        "ShortExemptVolume": pd.to_numeric(ddf.get("ShortExemptVolume"), errors="coerce"),
        "TotalVolume": pd.to_numeric(ddf.get("TotalVolume"), errors="coerce"),
        "short_dollars": pd.to_numeric(ddf.get("short_dollars"), errors="coerce"),
        "total_dollars": pd.to_numeric(ddf.get("total_dollars"), errors="coerce"),
        "finra_source": "daily_details",
        "universe_n": pd.NA,
        "missing_n": pd.NA,
    })

    # Map sector/profile from existing enriched master
    prof_cols = [c for c in ["category", "subcategory", "industry", "longName", "sector", "subsector"] if c in m.columns]
    if prof_cols:
        prof = m[["symbol"] + prof_cols].dropna(subset=["symbol"]).drop_duplicates("symbol")
        base = base.merge(prof, on="symbol", how="left")
        print(f"[INFO] Attached profile cols: {prof_cols}")
    else:
        print("[WARN] Master has no profile cols. Daily rows unclassified.")

    # Remove existing rows for the dates we're updating
    ymds_update = sorted(base["ymd"].unique().tolist())
    before = len(m)
    m2 = m[~m["ymd"].isin(ymds_update)].copy()
    after_drop = len(m2)
    print(f"[INFO] Master before={before:,} after_drop={after_drop:,} days_updated={len(ymds_update)}")

    # Merge
    merged = pd.concat([m2, base], ignore_index=True)
    merged["ymd"] = merged["ymd"].astype(str)
    merged["symbol"] = merged["symbol"].astype(str).str.upper()
    merged = merged.sort_values(["ymd", "symbol"]).reset_index(drop=True)

    # Save
    out_path = Path(args.out) if args.out else master_path
    merged.to_csv(out_path, index=False)
    print(f"[OK] Updated master: {out_path} rows={len(merged):,}")
    
    # Show what columns we have
    print(f"[INFO] Columns in updated master: {list(merged.columns)}")


if __name__ == "__main__":
    main()
