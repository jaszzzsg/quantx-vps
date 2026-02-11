import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DETAILS_DIR = ROOT / "data" / "dix" / "details"
OUT_DIR = ROOT / "data" / "dix" / "summary" / "persistence"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Windows (configurable via environment)
DAILY_LOOKBACK = int(os.environ.get("DIX_DAILY_LOOKBACK", "10"))   # trading days
WEEKLY_LOOKBACK = int(os.environ.get("DIX_WEEKLY_LOOKBACK", "6"))  # weeks
TOP_N_DAILY = int(os.environ.get("DIX_TOP_N_DAILY", "30"))
TOP_N_WEEKLY = int(os.environ.get("DIX_TOP_N_WEEKLY", "30"))


def get_recent_daily_files(days_back: int = 30) -> list[Path]:
    """Get daily detail files from last N calendar days."""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days_back)).strftime("%Y%m%d")
    files = sorted(DETAILS_DIR.glob("diy_dix_details_*_ibkr.csv"))
    
    recent = []
    for f in files:
        # Extract YYYYMMDD from filename
        parts = f.name.split("_")
        if len(parts) >= 4:
            ymd = parts[3]
            if ymd >= cutoff:
                recent.append(f)
    
    return sorted(recent)


def load_daily_details(files: list[Path]) -> pd.DataFrame:
    """Load and combine multiple daily detail files."""
    frames = []
    for f in files:
        ymd = f.name.split("_")[3]
        df = pd.read_csv(f)
        df["ymd"] = ymd
        df["Symbol"] = df["Symbol"].astype(str).str.upper().str.strip()
        
        # Ensure numeric columns
        for col in ["short_dollars", "total_dollars", "ShortVolume", "TotalVolume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        frames.append(df)
    
    if not frames:
        return pd.DataFrame()
    
    combined = pd.concat(frames, ignore_index=True)
    combined["ymd_dt"] = pd.to_datetime(combined["ymd"], format="%Y%m%d")
    return combined.sort_values("ymd_dt")


def week_start_monday(ts: pd.Timestamp) -> pd.Timestamp:
    """Get Monday of the week for a given timestamp."""
    return (ts - pd.to_timedelta(ts.weekday(), unit="D")).normalize()


def phase_label(streak: int) -> str:
    """Label accumulation phase based on weekly streak."""
    if streak <= 1:
        return "New"
    elif streak <= 3:
        return "Early"
    elif streak <= 6:
        return "Building"
    else:
        return "Institutional"


def main():
    print("[PERSISTENCE] Starting DIX persistence analysis...")
    
    # Load recent daily files
    files = get_recent_daily_files(days_back=90)  # 3 months buffer
    print(f"[INFO] Found {len(files)} daily detail files (last 90 days)")
    
    if not files:
        print("[ERROR] No daily detail files found!")
        return
    
    # Show file range
    first_ymd = files[0].name.split("_")[3]
    last_ymd = files[-1].name.split("_")[3]
    print(f"[INFO] Date range: {first_ymd} -> {last_ymd}")
    
    df = load_daily_details(files)
    
    if df.empty:
        print("[ERROR] No data loaded from daily files!")
        return
    
    print(f"[INFO] Loaded {len(df):,} rows from {df['ymd'].nunique()} trading days")
    
    # ===== DAILY PERSISTENCE (Top N by short_dollars) =====
    print(f"\n[DAILY] Analyzing Top {TOP_N_DAILY} tickers by short_dollars...")
    
    # Get top N per day
    top_daily = (
        df.sort_values(["ymd", "short_dollars"], ascending=[True, False])
          .groupby("ymd", as_index=False)
          .head(TOP_N_DAILY)
    )
    
    # Build presence sets per day
    days = sorted(top_daily["ymd"].unique())
    presence_by_day = {
        day: set(top_daily[top_daily["ymd"] == day]["Symbol"])
        for day in days
    }
    
    # Get last N trading days
    recent_days = days[-DAILY_LOOKBACK:]
    latest_day = recent_days[-1]
    
    print(f"[DAILY] Recent window: {recent_days[0]} -> {recent_days[-1]} ({len(recent_days)} days)")
    
    # Calculate days_active for latest day only
    latest_symbols = presence_by_day[latest_day]
    daily_results = []
    
    for sym in sorted(latest_symbols):
        count = sum(1 for d in recent_days if sym in presence_by_day.get(d, set()))
        daily_results.append({
            "ymd": latest_day,
            "Symbol": sym,
            f"days_active_{DAILY_LOOKBACK}": count
        })
    
    daily_df = pd.DataFrame(daily_results)
    
    # Merge with latest day's data
    latest_data = top_daily[top_daily["ymd"] == latest_day].copy()
    latest_data = latest_data.merge(daily_df, on=["ymd", "Symbol"], how="left")
    latest_data[f"days_active_{DAILY_LOOKBACK}"] = latest_data[f"days_active_{DAILY_LOOKBACK}"].fillna(0).astype(int)
    
    # Save daily persistence
    out_daily = OUT_DIR / f"daily_top{TOP_N_DAILY}_persistence_{latest_day}.csv"
    latest_data.to_csv(out_daily, index=False)
    print(f"[DAILY] Saved: {out_daily}")
    
    # ===== WEEKLY PERSISTENCE (Top N by weekly_short_dollars) =====
    print(f"\n[WEEKLY] Analyzing Top {TOP_N_WEEKLY} tickers by weekly short_dollars...")
    
    # Assign week_start (Monday)
    df["week_start"] = df["ymd_dt"].apply(week_start_monday)
    
    # Aggregate by week
    weekly = (
        df.groupby(["week_start", "Symbol"], as_index=False)
          .agg(
              weekly_short_dollars=("short_dollars", "sum"),
              weekly_total_dollars=("total_dollars", "sum")
          )
    )
    weekly["short_ratio"] = weekly["weekly_short_dollars"] / weekly["weekly_total_dollars"]
    
    # Get top N per week
    top_weekly = (
        weekly.sort_values(["week_start", "weekly_short_dollars"], ascending=[True, False])
              .groupby("week_start", as_index=False)
              .head(TOP_N_WEEKLY)
    )
    
    weeks = sorted(top_weekly["week_start"].unique())
    
    if not weeks:
        print("[WEEKLY] No weekly data available!")
        return
    
    latest_week = weeks[-1]
    window_weeks = weeks[-WEEKLY_LOOKBACK:]
    
    print(f"[WEEKLY] Window: {window_weeks[0].date()} -> {window_weeks[-1].date()} ({len(window_weeks)} weeks)")
    
    # Build presence sets per week
    presence_by_week = {
        week: set(top_weekly[top_weekly["week_start"] == week]["Symbol"])
        for week in weeks
    }
    
    # Calculate weekly persistence for latest week
    latest_week_symbols = presence_by_week[latest_week]
    weekly_results = []
    
    for sym in sorted(latest_week_symbols):
        # Rolling count (how many weeks in window)
        rolling_count = sum(1 for w in window_weeks if sym in presence_by_week.get(w, set()))
        
        # Streak (consecutive weeks ending at latest)
        streak = 0
        for i in range(len(weeks) - 1, -1, -1):
            if sym in presence_by_week.get(weeks[i], set()):
                streak += 1
            else:
                break
        
        weekly_results.append({
            "week_start": latest_week,
            "Symbol": sym,
            f"weeks_active_{WEEKLY_LOOKBACK}": rolling_count,
            "week_streak": streak,
            "phase": phase_label(streak)
        })
    
    weekly_persist_df = pd.DataFrame(weekly_results)
    
    # Merge with latest week's data
    latest_week_data = top_weekly[top_weekly["week_start"] == latest_week].copy()
    latest_week_data = latest_week_data.merge(weekly_persist_df, on=["week_start", "Symbol"], how="left")
    latest_week_data[f"weeks_active_{WEEKLY_LOOKBACK}"] = latest_week_data[f"weeks_active_{WEEKLY_LOOKBACK}"].fillna(0).astype(int)
    latest_week_data["week_streak"] = latest_week_data["week_streak"].fillna(0).astype(int)
    latest_week_data["phase"] = latest_week_data["phase"].fillna("New")
    
    # Save weekly persistence
    week_end = (latest_week + pd.Timedelta(days=4)).date()
    out_weekly = OUT_DIR / f"weekly_top{TOP_N_WEEKLY}_persistence_{latest_week.date()}_{week_end}.csv"
    latest_week_data.to_csv(out_weekly, index=False)
    print(f"[WEEKLY] Saved: {out_weekly}")
    
    # Summary stats
    print(f"\n[SUMMARY]")
    print(f"  Daily Top {TOP_N_DAILY}: {len(latest_data)} tickers")
    print(f"  Weekly Top {TOP_N_WEEKLY}: {len(latest_week_data)} tickers")
    print(f"  Phases: {latest_week_data['phase'].value_counts().to_dict()}")
    print(f"\n✅ Persistence analysis complete!")


if __name__ == "__main__":
    main()
