#!/usr/bin/env python3
"""
Enhanced Daily Precious Metals DIX Report with Short Ratio and 5-Day Comparison
Sends Telegram notification with:
- Short ratio per category
- % change vs 5-day average
- Top 10 tickers by short dollars
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta
import requests
from pathlib import Path

# Add parent directory to path for imports
script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
sys.path.insert(0, str(project_root))

def load_telegram_config():
    """Load Telegram credentials from /etc/quantx/telegram.env"""
    config = {}
    env_file = '/etc/quantx/telegram.env'
    
    if not os.path.exists(env_file):
        print(f"ERROR: {env_file} not found")
        sys.exit(1)
    
    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                key, value = line.split('=', 1)
                config[key] = value.strip().strip('"').strip("'")
    
    return config['TELEGRAM_BOT_TOKEN'], config['TELEGRAM_CHAT_ID']

def send_telegram(message, bot_token, chat_id):
    """Send message to Telegram"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML'
    }
    
    try:
        response = requests.post(url, data=data, timeout=10)
        if response.status_code == 200:
            print("✅ Telegram sent successfully")
        else:
            print(f"❌ Telegram failed: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def get_latest_daily_file(details_dir):
    """Find the most recent daily details CSV file"""
    files = list(Path(details_dir).glob("diy_dix_details_*_ibkr.csv"))
    if not files:
        return None
    
    files.sort(reverse=True)
    return files[0]

def get_past_5_days_files(details_dir, latest_date):
    """Get the 5 daily files before the latest date"""
    files = []
    current_date = latest_date - timedelta(days=1)
    
    for _ in range(10):
        filename = f"diy_dix_details_{current_date.strftime('%Y%m%d')}_ibkr.csv"
        filepath = Path(details_dir) / filename
        
        if filepath.exists():
            files.append(filepath)
            if len(files) == 5:
                break
        
        current_date -= timedelta(days=1)
    
    return files

def calculate_category_metrics(df):
    """Calculate metrics per category with short ratio"""
    # Group by category - use actual column names
    grouped = df.groupby('category').agg({
        'short_dollars': 'sum',
        'ShortVolume': 'sum',
        'TotalVolume': 'sum'
    }).reset_index()
    
    # Calculate short ratio
    grouped['short_ratio'] = (grouped['ShortVolume'] / grouped['TotalVolume'] * 100).round(2)
    
    # Sort by short dollars descending
    grouped = grouped.sort_values('short_dollars', ascending=False)
    
    return grouped

def main():
    # Paths
    details_dir = '/root/projects/quantx_dix/data/dix/details'
    
    # Precious metals categories mapping
    precious_categories = {
        'Gold': ['GLD', 'IAU', 'SGOL', 'AAAU', 'BAR', 'GLDM'],
        'Silver': ['SLV', 'PSLV', 'SIVR'],
        'Gold 2x': ['UGL'],
        'Gold -2x': ['GLL'],
        'Silver 2x': ['AGQ'],
        'Silver -2x': ['ZSL'],
        'Gold Miners': ['GDX', 'RING'],
        'Silver Miners': ['SIL'],
        'Jr Gold Miners': ['GDXJ'],
        'Jr Silver Miners': ['SILJ'],
        'Miners -2x': ['DUST'],
        'Jr Miners -2x': ['JDST']
    }
    
    # Get latest file
    latest_file = get_latest_daily_file(details_dir)
    if not latest_file:
        print("❌ No daily details files found")
        sys.exit(1)
    
    # Extract date from filename
    date_str = latest_file.stem.split('_')[3]
    latest_date = datetime.strptime(date_str, '%Y%m%d')
    
    print(f"📊 Processing {latest_file.name}")
    
    # Load latest data
    df_latest = pd.read_csv(latest_file)
    
    # Filter precious metals
    df_latest['category'] = df_latest['Symbol'].apply(
        lambda x: next((cat for cat, tickers in precious_categories.items() if x in tickers), None)
    )
    df_pm = df_latest[df_latest['category'].notna()].copy()
    
    if df_pm.empty:
        print("❌ No precious metals data found")
        sys.exit(1)
    
    # Calculate latest metrics
    latest_metrics = calculate_category_metrics(df_pm)
    
    # Get past 5 days for comparison
    past_files = get_past_5_days_files(details_dir, latest_date)
    
    if len(past_files) == 5:
        # Load and combine past 5 days
        past_dfs = []
        for f in past_files:
            df_temp = pd.read_csv(f)
            df_temp['category'] = df_temp['Symbol'].apply(
                lambda x: next((cat for cat, tickers in precious_categories.items() if x in tickers), None)
            )
            past_dfs.append(df_temp[df_temp['category'].notna()])
        
        df_past = pd.concat(past_dfs, ignore_index=True)
        
        # Calculate 5-day average per category
        past_metrics = df_past.groupby('category').agg({
            'short_dollars': 'mean'
        }).reset_index()
        past_metrics.rename(columns={'short_dollars': 'avg_5day'}, inplace=True)
        
        # Merge with latest
        latest_metrics = latest_metrics.merge(past_metrics, on='category', how='left')
        latest_metrics['pct_change'] = ((latest_metrics['short_dollars'] - latest_metrics['avg_5day']) / latest_metrics['avg_5day'] * 100).round(1)
    else:
        print(f"⚠️ Only found {len(past_files)} days for comparison (need 5)")
        latest_metrics['avg_5day'] = None
        latest_metrics['pct_change'] = None
    
    # Build Telegram message
    msg_lines = [f"💰 <b>Precious Metals DIX - {latest_date.strftime('%Y%m%d')}</b>\n"]
    
    # Category totals with short ratio and 5-day comparison
    msg_lines.append("<b>Category Totals:</b>")
    for _, row in latest_metrics.iterrows():
        short_b = row['short_dollars'] / 1e9
        ratio = row['short_ratio']
        
        line = f"  {row['category']}: ${short_b:.2f}B (SR: {ratio:.1f}%"
        
        if pd.notna(row['pct_change']):
            sign = "+" if row['pct_change'] > 0 else ""
            line += f", {sign}{row['pct_change']:.1f}% vs 5D avg"
        
        line += ")"
        msg_lines.append(line)
    
    # Top 10 tickers - use actual column names
    top10 = df_pm.nlargest(10, 'short_dollars')[['Symbol', 'category', 'short_dollars', 'ShortVolume', 'TotalVolume']].copy()
    top10['short_ratio'] = (top10['ShortVolume'] / top10['TotalVolume'] * 100).round(1)
    
    msg_lines.append("\n<b>Top 10 Tickers:</b>")
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        short_m = row['short_dollars'] / 1e6
        msg_lines.append(f"{i:2d}. {row['Symbol']:5s} ({row['category']}) ${short_m:.0f}M (SR: {row['short_ratio']:.1f}%)")
    
    # Overall bias
    gold_total = latest_metrics[latest_metrics['category'].str.contains('Gold', na=False)]['short_dollars'].sum()
    silver_total = latest_metrics[latest_metrics['category'].str.contains('Silver', na=False)]['short_dollars'].sum()
    
    if gold_total > silver_total * 1.5:
        bias = "Gold bias"
    elif silver_total > gold_total * 1.5:
        bias = "Silver bias"
    else:
        bias = "Balanced gold/silver flow"
    
    msg_lines.append(f"\n<b>BIAS:</b> {bias}")
    
    # Send
    message = "\n".join(msg_lines)
    print("\n" + "="*50)
    print(message.replace('<b>', '').replace('</b>', ''))
    print("="*50)
    
    bot_token, chat_id = load_telegram_config()
    send_telegram(message, bot_token, chat_id)

if __name__ == "__main__":
    main()