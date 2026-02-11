import io
import re
import time
import os
import requests
import pandas as pd
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

from ib_insync import IB, Stock, util

# Direct CDN URLs - no scraping needed!
FINRA_CDN_URLS = [
    "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt",
    "https://cdn.finra.org/equity/regsho/daily/FNQCshvol{ymd}.txt",
    "https://cdn.finra.org/equity/regsho/daily/FNRAshvol{ymd}.txt",
    "https://cdn.finra.org/equity/regsho/daily/FNSQshvol{ymd}.txt",
    "https://cdn.finra.org/equity/regsho/daily/FNYXshvol{ymd}.txt",
    "https://cdn.finra.org/equity/regsho/daily/FORFshvol{ymd}.txt",
]

TOP_N_TICKERS = 1200
MIN_TOTAL_VOLUME = 200000


def pick_ymd() -> str:
    if len(sys.argv) >= 2 and re.fullmatch(r"\d{8}", sys.argv[1]):
        return sys.argv[1]
    
    env_ymd = os.environ.get("DIX_DATE", "").strip()
    if re.fullmatch(r"\d{8}", env_ymd):
        return env_ymd
    
    now_utc = datetime.now(timezone.utc)
    ny_hour = (now_utc.hour - 5) % 24
    
    if ny_hour >= 1:
        target_date = now_utc.date() - timedelta(days=1)
    else:
        target_date = now_utc.date() - timedelta(days=2)
    
    while target_date.weekday() >= 5:
        target_date -= timedelta(days=1)
    
    return target_date.strftime("%Y%m%d")


def get_daily_file_urls_for_date(ymd: str) -> list[str]:
    """Directly construct FINRA CDN URLs - no scraping!"""
    valid_urls = []
    for url_template in FINRA_CDN_URLS:
        url = url_template.format(ymd=ymd)
        try:
            r = requests.head(url, timeout=10)
            if r.status_code == 200:
                valid_urls.append(url)
        except Exception:
            continue
    return valid_urls


def load_pipe_delimited(url: str) -> pd.DataFrame:
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    raw = r.content.decode("utf-8", errors="replace")
    df = pd.read_csv(io.StringIO(raw), sep="|")
    df.columns = [c.strip() for c in df.columns]
    return df


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    required = ["Symbol", "ShortVolume", "ShortExemptVolume", "TotalVolume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns {missing}. Got: {df.columns.tolist()}")
    return df[required]


def get_top_n_tickers_by_volume(agg: pd.DataFrame, top_n: int, min_vol: int) -> pd.DataFrame:
    agg = agg[agg["TotalVolume"] >= min_vol].copy()
    agg = agg.sort_values("TotalVolume", ascending=False).head(top_n)
    return agg


def finra_to_ibkr_symbol(finra_symbol: str) -> str:
    return finra_symbol.replace(" ", ".")


def ibkr_close_for_date(ib: IB, symbol: str, ymd: str) -> float | None:
    contract = Stock(symbol, "SMART", "USD")
    try:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=f"{ymd} 23:59:59",
            durationStr="2 D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
    except Exception:
        return None
    
    if not bars:
        return None

    df = util.df(bars)
    if df.empty:
        return None

    df["date"] = pd.to_datetime(df["date"]).dt.date
    target = pd.to_datetime(ymd, format="%Y%m%d").date()
    row = df.loc[df["date"] == target]
    
    if row.empty:
        return float(df.iloc[-1]["close"])
    return float(row.iloc[0]["close"])


if __name__ == "__main__":
    ymd = pick_ymd()
    print(f"[DIX DAILY] Target date: {ymd}")
    print(f"[DIX DAILY] Current time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"[DIX DAILY] Strategy: Top {TOP_N_TICKERS} (direct CDN, no scraping)")
    
    print("\n[STEP 1/3] Fetching FINRA data (direct CDN)...")
    urls = get_daily_file_urls_for_date(ymd)
    print(f"  FINRA files found: {len(urls)}")
    for u in urls:
        print(f"    {u}")
    
    if not urls:
        print(f"\n❌ FAIL: No FINRA files for {ymd}")
        sys.exit(1)

    frames = []
    for u in urls:
        df = load_pipe_delimited(u)
        df = normalize_cols(df)
        frames.append(df)
    
    all_df = pd.concat(frames, ignore_index=True)
    agg = (
        all_df.groupby("Symbol", as_index=False)[
            ["ShortVolume", "ShortExemptVolume", "TotalVolume"]
        ].sum()
    )

    agg = get_top_n_tickers_by_volume(agg, TOP_N_TICKERS, MIN_TOTAL_VOLUME)
    print(f"  Top {TOP_N_TICKERS} selected: {len(agg)} symbols")

    print("\n[STEP 2/3] Fetching IBKR closes...")
    
    ib = IB()
    try:
        ib.connect("127.0.0.1", 4002, clientId=22)
        print("  ✓ Connected")
    except Exception as e:
        print(f"\n❌ FAIL: {e}")
        sys.exit(1)

    closes = []
    missing = 0
    symbols = agg["Symbol"].tolist()
    
    for i, finra_sym in enumerate(symbols, start=1):
        ibkr_sym = finra_to_ibkr_symbol(finra_sym)
        c = ibkr_close_for_date(ib, ibkr_sym, ymd)
        closes.append(c)
        if c is None:
            missing += 1
        if i % 50 == 0:
            pct_done = int((i / len(symbols)) * 100)
            print(f"  [{pct_done:>3}%] {i}/{len(symbols)} ({missing} missing)")
        time.sleep(0.02)

    ib.disconnect()
    print(f"  ✓ Fetched {len(symbols)} ({missing} missing)")

    print("\n[STEP 3/3] Computing DIX...")
    agg["close"] = closes
    agg = agg.dropna(subset=["close"]).copy()
    
    agg["short_dollars"] = agg["ShortVolume"] * agg["close"]
    agg["total_dollars"] = agg["TotalVolume"] * agg["close"]

    diy_dix = agg["short_dollars"].sum() / agg["total_dollars"].sum()
    print(f"  DIY_DIX: {diy_dix:.4f}")

    print(f"\n  Top 10 by short_dollars:")
    top10 = agg.nlargest(10, "short_dollars")
    for i, (_, r) in enumerate(top10.iterrows(), start=1):
        print(f"    {i:2}. {r['Symbol']:6s} ${float(r['short_dollars'])/1e6:>7.1f}M")

    BASE_DIR = Path(__file__).resolve().parents[2]
    OUT_DIR = BASE_DIR / "data" / "dix" / "details"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_csv = OUT_DIR / f"diy_dix_details_{ymd}_ibkr.csv"
    agg.to_csv(out_csv, index=False)
    print(f"\n  ✓ Saved: {out_csv}")
    print(f"\n✅ SUCCESS")
