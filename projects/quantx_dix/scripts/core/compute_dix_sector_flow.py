#!/usr/bin/env python3
import argparse
import os
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--details_csv", required=True, help="Daily DIX details CSV (Symbol.. total_dollars etc)")
    ap.add_argument("--profile_cache", required=True, help="IBKR symbol profile cache CSV (symbol,industry,category,subcategory,...)")
    ap.add_argument("--out_dir", required=True, help="Output directory (summary)")
    ap.add_argument("--date", required=True, help="YYYYMMDD")
    args = ap.parse_args()

    details = pd.read_csv(args.details_csv)
    prof = pd.read_csv(args.profile_cache)

    # normalize keys
    details["Symbol"] = details["Symbol"].astype(str).str.upper()
    prof["symbol"] = prof["symbol"].astype(str).str.upper()

    merged = details.merge(prof, left_on="Symbol", right_on="symbol", how="left")

    missing_industry = merged["industry"].isna().sum() if "industry" in merged.columns else len(merged)
    print(f"Merged rows: {len(merged)} | Missing industry: {missing_industry}")

    os.makedirs(args.out_dir, exist_ok=True)

    # 1) Sector flow (% of total dollars by industry)
    total_all = merged["total_dollars"].sum()
    sector = (
        merged.groupby("industry", dropna=False)["total_dollars"]
        .sum()
        .reset_index()
        .sort_values("total_dollars", ascending=False)
    )
    sector["pct_total_dollars"] = sector["total_dollars"] / total_all if total_all != 0 else 0.0
    out_sector = os.path.join(args.out_dir, f"dix_sector_flow_{args.date}.csv")
    sector.to_csv(out_sector, index=False)

    # 2) Top 20 tickers by total_dollars (with sector fields)
    cols = [
        "Symbol","close","ShortVolume","TotalVolume","short_dollars","total_dollars",
        "industry","category","subcategory","longName","primaryExchange"
    ]
    keep = [c for c in cols if c in merged.columns]
    top20 = merged.sort_values("total_dollars", ascending=False)[keep].head(20)
    out_top = os.path.join(args.out_dir, f"dix_top20_by_dollars_{args.date}.csv")
    top20.to_csv(out_top, index=False)

    print("Saved:", out_sector)
    print("Saved:", out_top)

    print("\nTop 10 sectors by $ flow:")
    print(sector.head(10).to_string(index=False))

if __name__ == "__main__":
    main()
