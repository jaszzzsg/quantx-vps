#!/usr/bin/env python3
"""
Real-time progress monitor for 6Y chunked DIX fetch
Shows progress bar, ETA, speed, and current status
"""

import time
import sys
from pathlib import Path
from datetime import datetime, timedelta

# ANSI colors for terminal
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def parse_log_for_progress(log_path: Path) -> dict:
    """Parse log file to extract current progress."""
    if not log_path.exists():
        return None
    
    lines = log_path.read_text().splitlines()
    
    # Find last progress line: "[XX%] Day N/M ..."
    for line in reversed(lines):
        if "Day " in line and "/" in line:
            try:
                # Extract: [10%] Day 20/185 20200506 | 782 syms | 6.9 d/hr | ETA: 23.9h
                parts = line.split()
                
                # Get percentage
                pct_str = parts[0].strip('[]%')
                pct = int(pct_str)
                
                # Get day numbers
                day_part = [p for p in parts if '/' in p and 'Day' not in p][0]
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
                
                return {
                    'percent': pct,
                    'current_day': current,
                    'total_days': total,
                    'date': ymd,
                    'speed': speed,
                    'eta_hours': eta_hours,
                }
            except:
                continue
    
    return None


def draw_progress_bar(percent: int, width: int = 50) -> str:
    """Draw a fancy progress bar."""
    filled = int(width * percent / 100)
    bar = '█' * filled + '░' * (width - filled)
    return f"[{bar}] {percent}%"


def format_time(hours: float) -> str:
    """Format hours into human-readable time."""
    if hours < 1:
        return f"{int(hours * 60)}m"
    elif hours < 24:
        return f"{hours:.1f}h"
    else:
        days = int(hours / 24)
        remaining_hours = hours % 24
        return f"{days}d {remaining_hours:.1f}h"


def monitor_chunk(chunk_name: str, log_pattern: str):
    """Monitor a chunk's progress in real-time."""
    
    base_dir = Path(__file__).resolve().parents[2]
    logs_dir = base_dir / "logs"
    
    # Find the log file
    log_files = sorted(logs_dir.glob(log_pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    
    if not log_files:
        print(f"{Colors.RED}✗ No log file found matching: {log_pattern}{Colors.RESET}")
        print(f"Looking in: {logs_dir}")
        return
    
    log_path = log_files[0]
    
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}📊 Monitoring {chunk_name}{Colors.RESET}")
    print(f"Log: {log_path.name}")
    print(f"{Colors.CYAN}{'='*70}{Colors.RESET}\n")
    
    last_update = None
    
    try:
        while True:
            progress = parse_log_for_progress(log_path)
            
            if not progress:
                print(f"{Colors.YELLOW}⏳ Waiting for progress data...{Colors.RESET}", end='\r')
                time.sleep(5)
                continue
            
            # Clear line and show progress
            sys.stdout.write('\033[2K\r')  # Clear line
            
            # Progress bar
            bar = draw_progress_bar(progress['percent'])
            print(f"{Colors.GREEN}{bar}{Colors.RESET}")
            
            # Stats
            print(f"📅 Date:     {Colors.CYAN}{progress['date']}{Colors.RESET}")
            print(f"📈 Progress: {Colors.YELLOW}{progress['current_day']}/{progress['total_days']} days{Colors.RESET}")
            print(f"⚡ Speed:    {Colors.GREEN}{progress['speed']:.1f} days/hour{Colors.RESET}")
            print(f"⏰ ETA:      {Colors.BLUE}{format_time(progress['eta_hours'])}{Colors.RESET}")
            
            # Estimated completion time
            eta_dt = datetime.now() + timedelta(hours=progress['eta_hours'])
            print(f"🏁 Finishes: {Colors.BOLD}{eta_dt.strftime('%Y-%m-%d %H:%M SGT')}{Colors.RESET}")
            
            print(f"\n{Colors.CYAN}{'─'*70}{Colors.RESET}")
            print(f"Press Ctrl+C to stop monitoring (fetch continues in background)")
            print(f"{Colors.CYAN}{'─'*70}{Colors.RESET}\n")
            
            last_update = datetime.now()
            
            # Wait before next update
            time.sleep(10)
            
            # Move cursor up to overwrite
            for _ in range(10):
                sys.stdout.write('\033[F')  # Move up
                sys.stdout.write('\033[2K')  # Clear line
            
    except KeyboardInterrupt:
        print(f"\n\n{Colors.GREEN}✓ Monitoring stopped. Chunk fetch continues in background.{Colors.RESET}")
        print(f"Resume monitoring: python {__file__} {chunk_name}")


def main():
    chunks = {
        '2020': 'chunk_2020_FINAL_*.log',
        '2021': 'chunk_2021_*.log',
        '2022': 'chunk_2022_*.log',
        '2023': 'chunk_2023_*.log',
        '2024': 'chunk_2024_*.log',
        '2025': 'chunk_2025_*.log',
    }
    
    if len(sys.argv) < 2:
        print(f"{Colors.BOLD}Usage:{Colors.RESET}")
        print(f"  python {sys.argv[0]} <chunk_year>")
        print(f"\n{Colors.BOLD}Available chunks:{Colors.RESET}")
        for year in chunks.keys():
            print(f"  - {year}")
        print(f"\n{Colors.BOLD}Example:{Colors.RESET}")
        print(f"  python {sys.argv[0]} 2020")
        sys.exit(1)
    
    chunk_year = sys.argv[1]
    
    if chunk_year not in chunks:
        print(f"{Colors.RED}✗ Unknown chunk: {chunk_year}{Colors.RESET}")
        print(f"Available: {', '.join(chunks.keys())}")
        sys.exit(1)
    
    monitor_chunk(f"Chunk {chunk_year}", chunks[chunk_year])


if __name__ == "__main__":
    main()
