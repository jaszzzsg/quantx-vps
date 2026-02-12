from __future__ import annotations

import os
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
DETAILS_DIR = ROOT / "data" / "dix" / "details"
SUMMARY_DIR = ROOT / "data" / "dix" / "summary"
PERSIST_DIR = ROOT / "data" / "dix" / "summary" / "persistence"
TELEGRAM_ENV = Path("/etc/quantx/telegram.env")
HISTORY_DIR = ROOT / "data" / "dix" / "history"
ETF_MASTER = ROOT / "data" / "etf_classification_master.csv"
ENRICHED_GLOB = "*_enriched.csv"

SUMMARY_DIR.mkdir(parents=True, exist_ok=True)

PRECIOUS_SYMBOLS = {"GLD","IAU","SLV","SIVR","PPLT","PALL","GDX","GDXJ","SIL","SILJ","SGOL","PHYS","PSLV","SLV3","GDXU","NUGT","JNUG","DUST","JDST","UGL","GLL","AGQ","ZSL","USLV","DSLV","SILJ"}
PRECIOUS_KEYWORDS = ("gold","silver","precious","platinum","palladium","bullion","metals","mining","miners")

def load_telegram_env() -> Dict[str, str]:
    env = {}
    if TELEGRAM_ENV.exists():
        for line in TELEGRAM_ENV.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    env["TELEGRAM_BOT_TOKEN"] = os.getenv("TELEGRAM_BOT_TOKEN", env.get("TELEGRAM_BOT_TOKEN", ""))
    env["TELEGRAM_CHAT_ID"] = os.getenv("TELEGRAM_CHAT_ID", env.get("TELEGRAM_CHAT_ID", ""))
    return env

def load_etf_master() -> pd.DataFrame:
    if not ETF_MASTER.exists():
        return pd.DataFrame(columns=["ticker","sector","subsector","leverage","direction"])
    df = pd.read_csv(ETF_MASTER)
    df["Symbol"] = df["ticker"].astype(str).str.upper()
    return df[["Symbol","sector","subsector","leverage","direction"]].drop_duplicates("Symbol")

def load_ibkr_profile_cache() -> pd.DataFrame:
    """Load IBKR symbol profile cache for sector data (496 symbols)"""
    cache_paths = [
        ROOT / "scripts" / "data" / "ibkr_symbol_profile_cache.csv",
        ROOT / "data" / "ibkr_symbol_profile_cache.csv",
    ]
    for p in cache_paths:
        if p.exists():
            df = pd.read_csv(p)
            df["Symbol"] = df["symbol"].astype(str).str.upper()
            # Map IBKR fields to our standard names
            # Note: 'industry' contains sector-level data (e.g., "Technology", "Financial")
            # 'category' contains subsector data (e.g., "Computers", "Banks")
            df["sector"] = df.get("industry", "").astype(str).fillna("")
            df["subsector"] = df.get("category", "").astype(str).fillna("")
            df["industry"] = df.get("subcategory", "").astype(str).fillna("")
            df["longName"] = df.get("longName", "").astype(str).fillna("")
            return df[["Symbol", "sector", "subsector", "industry", "longName"]].drop_duplicates("Symbol")
    return pd.DataFrame(columns=["Symbol", "sector", "subsector", "industry", "longName"])

def last_completed_mf_window(today_utc: datetime) -> Tuple[str, str]:
    x = today_utc.date() - timedelta(days=1)
    while x.weekday() != 4:
        x -= timedelta(days=1)
    fri = x
    mon = fri - timedelta(days=4)
    return mon.strftime("%Y%m%d"), fri.strftime("%Y%m%d")

def ymds_between(start_ymd: str, end_ymd: str) -> List[str]:
    s = datetime.strptime(start_ymd, "%Y%m%d").date()
    e = datetime.strptime(end_ymd, "%Y%m%d").date()
    out = []
    d = s
    while d <= e:
        out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out

def load_enriched_profile() -> pd.DataFrame:
    files = sorted(HISTORY_DIR.glob(ENRICHED_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return pd.DataFrame(columns=["Symbol", "sector", "subsector", "industry", "longName"])
    df = pd.read_csv(files[0])
    if "symbol" in df.columns:
        df["Symbol"] = df["symbol"].astype(str).str.upper()
    elif "Symbol" in df.columns:
        df["Symbol"] = df["Symbol"].astype(str).str.upper()
    if "sector" not in df.columns:
        df["sector"] = df.get("category", "")
    if "subsector" not in df.columns:
        df["subsector"] = df.get("subcategory", "")
    for c in ["sector", "subsector", "industry", "longName"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).fillna("")
    return df[["Symbol", "sector", "subsector", "industry", "longName"]].drop_duplicates("Symbol")

def precious_override(symbol, long_name, sector, subsector, industry) -> bool:
    if (symbol or "").upper().strip() in PRECIOUS_SYMBOLS:
        return True
    # Handle NaN values (float NaN is truthy, so "or" trick doesn't work)
    def safe_str(x):
        return "" if pd.isna(x) else str(x)
    blob = " ".join([safe_str(long_name), safe_str(sector), safe_str(subsector), safe_str(industry)]).lower()
    return any(k in blob for k in PRECIOUS_KEYWORDS)

def read_daily_details(ymd: str) -> Optional[pd.DataFrame]:
    p = DETAILS_DIR / f"diy_dix_details_{ymd}_ibkr.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    df["ymd"] = ymd
    df["Symbol"] = df["Symbol"].astype(str).str.upper()
    for c in ["short_dollars", "total_dollars"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    return df

def load_persistence() -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    daily_files = sorted(PERSIST_DIR.glob("daily_top*_persistence_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    weekly_files = sorted(PERSIST_DIR.glob("weekly_top*_persistence_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    daily_df = None
    weekly_df = None
    
    if daily_files:
        daily_df = pd.read_csv(daily_files[0])
        daily_df["Symbol"] = daily_df["Symbol"].astype(str).str.upper()
        # Get the days_active column name dynamically
        days_col = [c for c in daily_df.columns if c.startswith("days_active_")]
        if days_col:
            daily_df = daily_df[["Symbol", days_col[0]]].rename(columns={days_col[0]: "days_active"})
    
    if weekly_files:
        weekly_df = pd.read_csv(weekly_files[0])
        weekly_df["Symbol"] = weekly_df["Symbol"].astype(str).str.upper()
        keep_cols = ["Symbol"]
        for c in ["weeks_active_6", "week_streak", "phase"]:
            if c in weekly_df.columns:
                keep_cols.append(c)
        weekly_df = weekly_df[keep_cols]
    
    return daily_df, weekly_df

def risk_score_from_short_ratio(short_ratio: float) -> int:
    if not math.isfinite(short_ratio):
        return 50
    return max(0, min(100, int(round(100.0 * (1.0 - short_ratio)))))

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default=None, help="Override window start YYYYMMDD")
    parser.add_argument("--end", default=None, help="Override window end YYYYMMDD")
    args = parser.parse_args()

    today = datetime.now(timezone.utc)
    if args.start and args.end:
        mon, fri = args.start, args.end
    else:
        mon, fri = last_completed_mf_window(today)
    ymds = ymds_between(mon, fri)

    print(f"[WEEKLY] Window: {mon} -> {fri}")

    # Load profile sources
    prof = load_enriched_profile()
    etf_prof = load_etf_master()
    ibkr_prof = load_ibkr_profile_cache()

    if not prof.empty:
        print('[INFO] Profile source: enriched master')
    if not ibkr_prof.empty:
        print(f'[INFO] IBKR profile cache: {len(ibkr_prof)} symbols')

    frames = []
    used_days = []
    for ymd in ymds:
        d = read_daily_details(ymd)
        if d is None:
            continue
        frames.append(d)
        used_days.append(ymd)

    if not frames:
        print("[ERROR] No daily detail files!")
        return

    df = pd.concat(frames, ignore_index=True)
    df["Symbol"] = df["Symbol"].astype(str).str.upper()
    
    # Merge enriched profile first
    df = df.merge(prof, on="Symbol", how="left")

    # Then merge IBKR profile cache (fills gaps from enriched)
    df = df.merge(ibkr_prof, on="Symbol", how="left", suffixes=("", "_ibkr"))
    for col in ["sector", "subsector", "industry", "longName"]:
        ibkr_col = f"{col}_ibkr"
        if ibkr_col in df.columns:
            # Fill empty values with IBKR data
            mask = (df[col].isna()) | (df[col] == "") | (df[col] == "nan")
            df.loc[mask, col] = df.loc[mask, ibkr_col]
    # Drop IBKR suffix columns
    df = df[[c for c in df.columns if not c.endswith("_ibkr")]]

    # Then merge ETF profile (overrides for ETFs)
    df = df.merge(etf_prof, on="Symbol", how="left", suffixes=("", "_etf"))
    df["sector"] = df["sector_etf"].fillna(df["sector"])
    df["subsector"] = df["subsector_etf"].fillna(df["subsector"])
    
    # Drop ETF columns
    df = df[[c for c in df.columns if not c.endswith("_etf")]]

    # Apply precious metals override
    is_prec = df.apply(lambda r: precious_override(r.get("Symbol",""), r.get("longName",""), r.get("sector",""), r.get("subsector",""), r.get("industry","")), axis=1).fillna(False).astype(bool)
    df.loc[is_prec, "sector"] = "Precious Metals"

    # Sector aggregation
    by_sector = df.groupby(["sector"], dropna=False).agg(short_dollars=("short_dollars", "sum"), total_dollars=("total_dollars", "sum"), names=("Symbol", "nunique")).reset_index()
    by_sector["short_ratio"] = by_sector["short_dollars"] / by_sector["total_dollars"]
    top5_sectors = by_sector.sort_values("total_dollars", ascending=False).head(6).copy()
    top5_sectors["short_ratio"] = top5_sectors["short_ratio"].round(3)

    # Ticker aggregation
    by_ticker = df.groupby(["Symbol", "sector"], dropna=False).agg(short_dollars=("short_dollars", "sum"), total_dollars=("total_dollars", "sum")).reset_index()
    by_ticker["short_ratio"] = by_ticker["short_dollars"] / by_ticker["total_dollars"]
    top20 = by_ticker.sort_values("short_dollars", ascending=False).head(20).copy()
    top20["short_ratio"] = top20["short_ratio"].round(3)

    # Load persistence
    daily_persist, weekly_persist = load_persistence()
    
    if daily_persist is not None:
        print(f"[INFO] Merging daily persistence (columns: {list(daily_persist.columns)})")
        top20 = top20.merge(daily_persist, on="Symbol", how="left")
    
    if weekly_persist is not None:
        print(f"[INFO] Merging weekly persistence (columns: {list(weekly_persist.columns)})")
        top20 = top20.merge(weekly_persist, on="Symbol", how="left")

    # Calculate metrics
    total_short = float(df["short_dollars"].sum())
    total_total = float(df["total_dollars"].sum())
    short_ratio = (total_short / total_total) if total_total > 0 else float("nan")
    score = risk_score_from_short_ratio(short_ratio)

    # Save outputs
    out_sector = SUMMARY_DIR / f"weekly_sector_flow_{mon}-{fri}.csv"
    out_top20 = SUMMARY_DIR / f"weekly_top20_short_dollars_{mon}-{fri}.csv"
    top5_sectors.to_csv(out_sector, index=False)
    top20.to_csv(out_top20, index=False)

    # Build Telegram message
    lines = []
    label = "QuantX DIX Early Weekly Report" if (args.start and args.end) else "QuantX DIX Weekly Report"
    lines.append(label)
    lines.append(f"{mon} → {fri} (Days: {len(used_days)})")
    lines.append(f"Risk Score: {score}/100 (sr={short_ratio:.3f})")
    lines.append("")
    lines.append("Top 6 Sectors:")
    for _, r in top5_sectors.iterrows():
        lines.append(f"• {str(r['sector'])[:25]} ${float(r['total_dollars'])/1e9:.1f}B sr={float(r['short_ratio']):.3f} ({int(r['names'])} names)")
    
    lines.append("")
    lines.append("Top 20 Tickers:")
    for i, (_, r) in enumerate(top20.iterrows(), start=1):
        sym = r["Symbol"]
        sec = str(r.get("sector", ""))[:15] if pd.notna(r.get("sector")) else ""
        sd = float(r["short_dollars"])
        sr = float(r["short_ratio"]) if math.isfinite(r["short_ratio"]) else 0.0
        
        extra = ""
        # Daily counter
        if "days_active" in r and pd.notna(r["days_active"]):
            extra += f" [{int(r['days_active'])}/10d]"
        # Weekly counter
        if "week_streak" in r and pd.notna(r["week_streak"]):
            extra += f" [{int(r['week_streak'])}w {r.get('phase','')}]"
        
        lines.append(f"{i:2}. {sym} ({sec}) ${sd/1e6:.0f}M sr={sr:.3f}{extra}")

    msg = "\n".join(lines)

    # Send Telegram
    env = load_telegram_env()
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        url = f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage"
        r = requests.post(url, json={"chat_id": env["TELEGRAM_CHAT_ID"], "text": msg, "disable_web_page_preview": True}, timeout=20)
        print(f"[OK] Telegram sent" if r.status_code == 200 else f"[WARN] Telegram failed {r.status_code}")

    print(f"[SAVED] {out_sector}")
    print(f"[SAVED] {out_top20}")
    print("✅ Weekly report complete!")

if __name__ == "__main__":
    main()
