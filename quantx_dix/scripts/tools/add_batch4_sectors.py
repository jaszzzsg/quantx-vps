#!/usr/bin/env python3
"""Add Batch 4 sector classifications"""
import pandas as pd

# ETFs to add
etf_additions = [
    ('VTWO', 'Equity', 'Small Cap', 'None', 'Long', 'Vanguard Russell 2000 ETF'),
    ('IUSB', 'Fixed Income', 'Aggregate Bond', 'None', 'Long', 'iShares Core Total USD Bond Market ETF'),
    ('ICSH', 'Fixed Income', 'Ultra-Short', 'None', 'Long', 'iShares Ultra Short-Term Bond ETF'),
    ('TFLO', 'Fixed Income', 'Floating Rate', 'None', 'Long', 'iShares Treasury Floating Rate Bond ETF'),
    ('PYLD', 'Fixed Income', 'High Yield', 'None', 'Long', 'PIMCO Access Income Fund'),
    ('SPHY', 'Fixed Income', 'High Yield', 'None', 'Short', 'SPDR Portfolio High Yield Bond ETF'),
    ('BITX', 'Equity', 'Bitcoin Miners', 'None', 'Long', '2x Bitcoin Strategy ETF'),
]

# Stocks to add
stock_additions = [
    ('GWRE', 'GWRE', 'Technology', 'Software', 'Application Software', 'Guidewire Software, Inc.', 'NYSE', 'NYSE'),
    ('OKTA', 'OKTA', 'Technology', 'Software', 'Security Software', 'Okta, Inc.', 'NASDAQ', 'NASDAQ'),
    ('GLXY', 'GLXY', 'Technology', 'Software', 'Application Software', 'Galaxy Digital Holdings Ltd.', 'NASDAQ', 'NASDAQ'),
    ('TSLG', 'TSLG', 'Technology', 'Semiconductors', 'Semiconductors', 'Tesla Inc.', 'NASDAQ', 'NASDAQ'),
    ('CG', 'CG', 'Financial', 'Investment Managers', 'Investment Managers', 'The Carlyle Group Inc.', 'NASDAQ', 'NASDAQ'),
    ('CART', 'CART', 'Consumer, Cyclical', 'Retail', 'Specialty Retail', 'Instacart (Maplebear Inc.)', 'NASDAQ', 'NASDAQ'),
    ('CRML', 'CRML', 'Technology', 'Software', 'Application Software', 'Critical Metals Corp.', 'NASDAQ', 'NASDAQ'),
    ('EXEL', 'EXEL', 'Healthcare', 'Biotechnology', 'Biotechnology', 'Exelixis, Inc.', 'NASDAQ', 'NASDAQ'),
    ('EGO', 'EGO', 'Basic Materials', 'Gold', 'Gold Mining', 'Eldorado Gold Corporation', 'NYSE', 'NYSE'),
    ('OVV', 'OVV', 'Energy', 'Oil & Gas', 'Oil & Gas Exploration', 'Ovintiv Inc.', 'NYSE', 'NYSE'),
    ('FIG', 'FIG', 'Financial', 'Investment Managers', 'Investment Managers', 'Fortress Investment Group', 'NYSE', 'NYSE'),
    ('VIK', 'VIK', 'Energy', 'Oil & Gas', 'Oil & Gas Exploration', 'Viking Holdings Ltd.', 'NYSE', 'NYSE'),
    ('CAVA', 'CAVA', 'Consumer, Cyclical', 'Restaurants', 'Restaurants', 'CAVA Group, Inc.', 'NYSE', 'NYSE'),
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