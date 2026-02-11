#!/usr/bin/env python3
"""
Live progress monitor for chunk 2020 fetch - optimized for VS Code terminal
Shows real-time progress with a visual progress bar
"""

import time
import sys
from pathlib import Path
from datetime import datetime, timedelta

LOG_FILE = Path("/root/projects/quantx_dix/logs/chunk_2020_FINAL_20260131_071207.log")

def parse_latest_progress(log_path: Path) -> dict:
    """Extract latest progress from log file."""
    if not log_path.exists():
        return None

    lines = log_path.read_text().splitlines()

    # Find last progress line: "[XX%] Day N/M ..."
    for line in reversed(lines):
        if "Day " in line and "/" in line and "ETA:" in line:
            try:
                # Parse: [  6%] Day 12/185 20200504 | 777 syms | 5.1 d/hr | ETA: 33.9h
                parts = line.split()

                # Get percentage (handle variable spacing)
                pct_str = None
                for p in parts:
                    if p.startswith('[') and '%]' in p:
                        pct_str = p.strip('[]%')
                        break
                if not pct_str:
                    continue
                pct = int(pct_str)

                # Get day numbers
                day_part = [p for p in parts if '/' in p][0]
                current, total = map(int, day_part.split('/'))

                # Get date
                ymd = [p for p in parts if len(p) == 8 and p.isdigit()][0]

                # Get speed
                speed = 0
                for i, p in enumerate(parts):
                    if p == "d/hr":
                        speed = float(parts[i-1])
                        break

                # Get ETA
                eta_hours = 0
                for i, p in enumerate(parts):
                    if p.startswith("ETA:"):
                        eta_str = parts[i+1].rstrip('h')
                        eta_hours = float(eta_str)
                        break

                # Get symbol count
                syms = 0
                for i, p in enumerate(parts):
                    if p == "syms":
                        syms = int(parts[i-1])
                        break

                return {
                    'percent': pct,
                    'current_day': current,
                    'total_days': total,
                    'date': ymd,
                    'speed': speed,
                    'eta_hours': eta_hours,
                    'symbols': syms,
                }
            except Exception as e:
                continue

    return None


def format_eta(hours: float) -> str:
    """Format ETA into human-readable time."""
    if hours < 1:
        return f"{int(hours * 60)}min"
    elif hours < 24:
        return f"{hours:.1f}h"
    else:
        days = int(hours / 24)
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours:.0f}h"


def draw_progress_bar(percent: int, width: int = 40) -> str:
    """Draw a simple progress bar."""
    filled = int(width * percent / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {percent:3d}%"


def main():
    print("=" * 70)
    print("📊 IBKR Chunk 2020 Fetch - Live Monitor")
    print("=" * 70)
    print("Press Ctrl+C to stop monitoring (fetch continues in background)\n")

    last_percent = -1
    no_data_count = 0

    try:
        while True:
            progress = parse_latest_progress(LOG_FILE)

            if not progress:
                no_data_count += 1
                if no_data_count > 60:  # 5 minutes with no data
                    print("\r⚠️  WARNING: No progress data for 5+ minutes. Check if process is stuck!", end='')
                else:
                    print(f"\r⏳ Waiting for progress data... ({no_data_count}s)          ", end='')
                time.sleep(5)
                continue

            no_data_count = 0

            # Show progress (update in place)
            bar = draw_progress_bar(progress['percent'], width=40)
            eta = format_eta(progress['eta_hours'])
            finish_time = datetime.now() + timedelta(hours=progress['eta_hours'])

            # Clear and redraw
            print(f"\r{bar}  ", end='')
            print(f"\n📅 Date: {progress['date']} | Day {progress['current_day']}/{progress['total_days']}  ", end='')
            print(f"\n📊 {progress['symbols']} symbols | Speed: {progress['speed']:.1f} days/hr  ", end='')
            print(f"\n⏰ ETA: {eta} | Finish: {finish_time.strftime('%b %d %H:%M')}  ", end='')
            print(f"\n{'─' * 70}  ", end='')

            # If percentage changed, add newline for history
            if progress['percent'] != last_percent:
                last_percent = progress['percent']
                print(f"\n✓ {datetime.now().strftime('%H:%M:%S')} - {progress['percent']}% complete")

            # Move cursor back up
            print("\r\033[5A", end='')

            time.sleep(5)

    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("✓ Monitoring stopped. Fetch continues in background.")
        print("=" * 70)


if __name__ == "__main__":
    main()
