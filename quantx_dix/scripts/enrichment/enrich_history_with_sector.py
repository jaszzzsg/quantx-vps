from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HIST_DIR = ROOT / "data" / "dix" / "history"
PROFILE_CACHE = ROOT / "data" / "ibkr_symbol_profile_cache.csv"

PRECIOUS_SYMBOLS = {
    "GLD","IAU","SLV","SIVR","PPLT","PALL",
    "GDX","GDXJ","SIL","SILJ",
    "SGOL","PHYS","PSLV",
    "SLV3","GDXU",
}
PRECIOUS_KEYWORDS = ("gold","silver","precious","platinum","palladium","bullion","metals","mining","miners")


def newest_history_file() -> Path:
    files = sorted(
        HIST_DIR.glob("diy_dix_history_6y_*_finraTop*_minVol*.csv"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError(f"No 6Y history files found in {HIST_DIR}")
    return files[0]


def load_profile() -> pd.DataFrame:
    if not PROFILE_CACHE.exists():
        raise FileNotFoundError(f"Missing profile cache: {PROFILE_CACHE}")
    p = pd.read_csv(PROFILE_CACHE)
    if "symbol" in p.columns:
        p["Symbol"] = p["symbol"].astype(str).str.upper()
    elif "Symbol" in p.columns:
        p["Symbol"] = p["Symbol"].astype(str).str.upper()
    else:
        raise ValueError("Profile cache must contain 'symbol' or 'Symbol' column.")
    for c in ["category", "subcategory", "industry", "longName"]:
        if c not in p.columns:
            p[c] = ""
        p[c] = p[c].astype(str)
    return p[["Symbol", "category", "subcategory", "industry", "longName"]].drop_duplicates("Symbol")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--infile", default="", help="Input history CSV (default: newest 6Y file)")
    ap.add_argument("--outfile", default="", help="Output enriched CSV (default: infile + _enriched)")
    args = ap.parse_args()

    infile = Path(args.infile) if args.infile else newest_history_file()
    df = pd.read_csv(infile)

    # normalize symbol col safely
    if "symbol" in df.columns:
        df["Symbol"] = df["symbol"]
    elif "Symbol" in df.columns:
        df["Symbol"] = df["Symbol"]
    else:
        raise ValueError("History file must contain 'symbol' or 'Symbol'.")

    df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
    # Remove 'NAN' strings created by astype(str)
    df.loc[df["Symbol"].isin(["NAN", "NONE", ""]), "Symbol"] = pd.NA

    prof = load_profile()
    out = df.merge(prof, on="Symbol", how="left")

    # sector fields
    out["sector"] = out.get("category", "").fillna("").astype(str)
    out["subsector"] = out.get("subcategory", "").fillna("").astype(str)
    out["industry"] = out.get("industry", "").fillna("").astype(str)
    out["longName"] = out.get("longName", "").fillna("").astype(str)

    # --- Vectorized Precious Metals tagging ---
    sym = out["Symbol"].fillna("").astype(str).str.upper().str.strip()
    mask_sym = sym.isin(PRECIOUS_SYMBOLS)

    blob = (
        out["longName"].fillna("").astype(str) + " " +
        out["sector"].fillna("").astype(str) + " " +
        out["subsector"].fillna("").astype(str) + " " +
        out["industry"].fillna("").astype(str)
    ).str.lower()

    mask_kw = False
    for k in PRECIOUS_KEYWORDS:
        mask_kw = mask_kw | blob.str.contains(k, na=False)

    prec_mask = mask_sym | mask_kw

    out.loc[prec_mask, "sector"] = "Precious Metals"
    out.loc[prec_mask, "subsector"] = "Gold/Silver/Platinum/Palladium"

    outfile = Path(args.outfile) if args.outfile else infile.with_name(infile.stem + "_enriched.csv")
    out.to_csv(outfile, index=False)

    print("[OK] Enriched history written:")
    print(f" - IN : {infile}")
    print(f" - OUT: {outfile}")
    print(f"[OK] Rows={len(out):,} | Unique symbols={out['Symbol'].nunique(dropna=True):,} | Precious tagged={int(prec_mask.sum()):,}")

if __name__ == "__main__":
    main()
