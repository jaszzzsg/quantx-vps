import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DETAILS_DIR = ROOT / "data" / "dix" / "details"
ETF_MASTER = ROOT / "data" / "etf_classification_master.csv"
ALERT_LOG = ROOT / "logs" / "unclassified_etfs.log"

def get_latest_daily_file() -> Path:
    files = sorted(DETAILS_DIR.glob("diy_dix_details_*_ibkr.csv"), reverse=True)
    if not files:
        raise FileNotFoundError("No daily detail files found!")
    return files[0]

def load_etf_master() -> set[str]:
    if not ETF_MASTER.exists():
        return set()
    df = pd.read_csv(ETF_MASTER)
    return set(df["ticker"].astype(str).str.upper())

def main():
    # Load latest daily file
    daily_file = get_latest_daily_file()
    ymd = daily_file.name.split("_")[3]
    
    print(f"[ALERT] Checking {daily_file.name} for unclassified ETFs...")
    
    df = pd.read_csv(daily_file)
    df["Symbol"] = df["Symbol"].astype(str).str.upper()
    
    # Get top 50 by short_dollars
    top50 = df.nlargest(50, "short_dollars")
    
    # Load ETF master
    known_etfs = load_etf_master()
    
    # Find unknowns
    unknown = []
    for sym in top50["Symbol"]:
        if sym not in known_etfs:
            # Simple heuristic: if ticker has common ETF patterns, flag it
            sym_str = str(sym)
            if any(x in sym_str for x in ["3", "L", "S", "U", "D", "X"]):
                unknown.append(sym)
    
    if unknown:
        msg = f"\n[{ymd}] ⚠️  UNCLASSIFIED ETFs IN TOP 50:\n"
        msg += "\n".join([f"  - {s}" for s in unknown])
        msg += f"\n\nTotal: {len(unknown)} tickers need manual classification"
        msg += f"\nAdd them to: {ETF_MASTER}\n"
        
        print(msg)
        
        # Log to file
        with open(ALERT_LOG, "a") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} {msg}\n")
    else:
        print(f"[OK] All Top 50 tickers are classified!")

if __name__ == "__main__":
    main()
