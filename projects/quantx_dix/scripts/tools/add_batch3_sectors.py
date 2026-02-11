#!/usr/bin/env python3
"""Add Batch 3 sector classifications"""
import pandas as pd

# ETFs to add
etf_additions = [
    ('INDA', 'Equity', 'India', 'None', 'Long', 'iShares MSCI India ETF'),
    ('MBB', 'Fixed Income', 'Mortgage-Backed Securities', 'None', 'Long', 'iShares MBS ETF'),
    ('TIP', 'Fixed Income', 'Inflation-Protected', 'None', 'Long', 'iShares TIPS Bond ETF'),
    ('VUSB', 'Fixed Income', 'Ultra-Short', 'None', 'Long', 'Vanguard Ultra-Short Bond ETF'),
    ('IYT', 'Equity', 'Transportation', 'None', 'Long', 'iShares Transportation Average ETF'),
    ('MINT', 'Fixed Income', 'Ultra-Short', 'None', 'Long', 'PIMCO Enhanced Short Maturity Active ETF'),
    ('GOVT', 'Fixed Income', 'US Treasury', 'None', 'Long', 'iShares U.S. Treasury Bond ETF'),
    ('IEI', 'Fixed Income', 'Intermediate Treasury', 'None', 'Long', 'iShares 3-7 Year Treasury Bond ETF'),
    ('IGIB', 'Fixed Income', 'Intermediate Credit', 'None', 'Long', 'iShares Intermediate Credit Bond ETF'),
]

# Stocks to add
stock_additions = [
    ('PRIV', 'PRIV', 'Financial', 'Investment Managers', 'Investment Managers', 'Beneficient', 'NASDAQ', 'NASDAQ'),
    ('RMBS', 'RMBS', 'Financial', 'Real Estate Investment Trusts', 'Mortgage REITs', 'Rambus Inc.', 'NASDAQ', 'NASDAQ'),
    ('FUSE', 'FUSE', 'Technology', 'Software', 'Infrastructure Software', 'Fusion Pharmaceuticals Inc.', 'NASDAQ', 'NASDAQ'),
    ('ARES', 'ARES', 'Financial', 'Investment Managers', 'Investment Managers', 'Ares Management Corporation', 'NYSE', 'NYSE'),
    ('IBKR', 'IBKR', 'Financial', 'Brokers & Intermediaries', 'Investment Brokers', 'Interactive Brokers Group, Inc.', 'NASDAQ', 'NASDAQ'),
    ('XPO', 'XPO', 'Industrial', 'Transportation & Logistics', 'Trucking', 'XPO, Inc.', 'NYSE', 'NYSE'),
    ('W', 'W', 'Consumer, Cyclical', 'Retail', 'Internet Retail', 'Wayfair Inc.', 'NYSE', 'NYSE'),
    ('MKSI', 'MKSI', 'Technology', 'Semiconductors', 'Semiconductor Equipment', 'MKS Instruments, Inc.', 'NASDAQ', 'NASDAQ'),
    ('KNX', 'KNX', 'Industrial', 'Conglomerates', 'Conglomerates', 'Knight-Swift Transportation Holdings Inc.', 'NYSE', 'NYSE'),
    ('DOCN', 'DOCN', 'Technology', 'Software', 'Infrastructure Software', 'DigitalOcean Holdings, Inc.', 'NYSE', 'NYSE'),
    ('BN', 'BN', 'Financial', 'Investment Managers', 'Investment Managers', 'Brookfield Corporation', 'NYSE', 'NYSE'),
]

# Load existing files
etf_file = '/root/projects/quantx_dix/data/etf_classification_master.csv'
stock_file = '/root/projects/quantx_dix/data/ibkr_symbol_profile_cache.csv'

# ETF update
df_etf = pd.read_csv(etf_file)
df_new_etf = pd.DataFrame(etf_additions, columns=['ticker', 'sector', 'subsector', 'leverage', 'direction', 'description'])
df_etf = pd.concat([df_etf, df_new_etf], ignore_index=True)
df_etf.drop_duplicates(subset=['ticker'], keep='first', inplace=True)
df_etf.to_csv(etf_file, index=False)
print(f"✅ ETF file updated: {len(df_new_etf)} new ETFs added (total: {len(df_etf)})")

# Stock update
df_stock = pd.read_csv(stock_file)
df_new_stock = pd.DataFrame(stock_additions, columns=['symbol', 'query_symbol', 'industry', 'category', 'subcategory', 'longName', 'exchange', 'primaryExchange'])
df_stock = pd.concat([df_stock, df_new_stock], ignore_index=True)
df_stock.drop_duplicates(subset=['symbol'], keep='first', inplace=True)
df_stock.to_csv(stock_file, index=False)
print(f"✅ Stock file updated: {len(df_new_stock)} new stocks added (total: {len(df_stock)})")

print(f"\n📊 Total classified: {len(df_etf)} ETFs + {len(df_stock)} stocks = {len(df_etf) + len(df_stock)}")
