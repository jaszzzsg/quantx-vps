#!/usr/bin/env python3
"""Add Batch 6 sector classifications — next tier unnamed from Feb 2-6 2026 weekly report"""
import pandas as pd

# ── ETFs (ticker, sector, subsector, leverage, direction, description) ──────────
etf_additions = [
    ('DOG',   'Equity',        'Dow Jones Inverse',       '1x',   'Short', 'ProShares Short Dow30'),
    ('SDOW',  'Equity',        'Dow Jones Inverse',       '3x',   'Short', 'ProShares UltraPro Short Dow30'),
    ('BINC',  'Fixed Income',  'Flexible Income',         'None', 'Long',  'BlackRock Flexible Income ETF'),
    ('PFF',   'Fixed Income',  'Preferred Securities',    'None', 'Long',  'iShares Preferred & Income Securities ETF'),
    ('SCHO',  'Fixed Income',  'Short Treasury',          'None', 'Long',  'Schwab Short-Term U.S. Treasury ETF'),
    ('AVEM',  'Equity',        'Emerging Markets',        'None', 'Long',  'Avantis Emerging Markets Equity ETF'),
    ('EMXC',  'Equity',        'Emerging Markets ex-China','None','Long',  'iShares MSCI Emerging Markets ex-China ETF'),
    ('SCHE',  'Equity',        'Emerging Markets',        'None', 'Long',  'Schwab Emerging Markets Equity ETF'),
    ('EWH',   'Equity',        'Hong Kong',               'None', 'Long',  'iShares MSCI Hong Kong ETF'),
    ('SCHV',  'Equity',        'Large Cap Value',         'None', 'Long',  'Schwab U.S. Large-Cap Value ETF'),
    ('SCHA',  'Equity',        'Small Cap',               'None', 'Long',  'Schwab U.S. Small-Cap ETF'),
    ('DFIV',  'Equity',        'International Value',     'None', 'Long',  'Dimensional International Value ETF'),
    ('MAGS',  'Equity',        'Mega Cap Growth',         'None', 'Long',  'Roundhill Magnificent Seven ETF'),
    ('IGM',   'Equity',        'Technology',              'None', 'Long',  'iShares Expanded Tech Sector ETF'),
    ('ITOT',  'Equity',        'Broad Market',            'None', 'Long',  'iShares Core S&P Total U.S. Stock Market ETF'),
    ('MSFU',  'Equity',        'MicroStrategy Bull',      '2x',   'Long',  'Defiance Daily Target 2X Long MSTR ETF'),
    ('BITI',  'Equity',        'Bitcoin Inverse',         '1x',   'Short', 'ProShares Short Bitcoin Strategy ETF'),
    ('BITU',  'Equity',        'Bitcoin Bull',            '2x',   'Long',  'ProShares Ultra Bitcoin ETF'),
    ('ETH',   'Equity',        'Ethereum',                'None', 'Long',  'Grayscale Ethereum Mini Trust ETF'),
    ('PLTZ',  'Equity',        'Palantir Bull',           '2x',   'Long',  'T-Rex 2X Long Palantir Daily Target ETF'),
    ('AMZD',  'Equity',        'Amazon Bear',             '2x',   'Short', 'GraniteShares 2x Short Amazon Daily ETP'),
    ('AMZU',  'Equity',        'Amazon Bull',             '2x',   'Long',  'GraniteShares 2x Long Amazon Daily ETP'),
    ('SVIX',  'Volatility',    'VIX Inverse',             '1x',   'Short', '-1x Short VIX Futures ETF'),
]

# ── Stocks (symbol, query_symbol, industry, category, subcategory, longName, exchange, primaryExchange)
stock_additions = [
    ('ALC',   'ALC',  'Healthcare',            'Medical Devices',          'Eye Care',                 'Alcon Inc.',                               'NYSE',   'NYSE'),
    ('QXO',   'QXO',  'Technology',            'Software',                 'Construction Technology',  'QXO Inc.',                                 'NASDAQ', 'NASDAQ'),
    ('PTON',  'PTON', 'Consumer Cyclical',     'Fitness',                  'Fitness Equipment',        'Peloton Interactive Inc.',                  'NASDAQ', 'NASDAQ'),
    ('BCS',   'BCS',  'Financial',             'Banking',                  'International Banks',      'Barclays PLC',                             'NYSE',   'NYSE'),
    ('UEC',   'UEC',  'Energy',               'Uranium',                   'Uranium Mining',           'Uranium Energy Corp.',                     'NYSE',   'NYSE'),
    ('CELH',  'CELH', 'Consumer Non-cyclical', 'Beverages',                'Energy Drinks',            'Celsius Holdings Inc.',                    'NASDAQ', 'NASDAQ'),
    ('EQNR',  'EQNR', 'Energy',               'Oil & Gas',                 'Oil & Gas Integrated',     'Equinor ASA',                              'NYSE',   'NYSE'),
    ('CNH',   'CNH',  'Industrial',            'Agricultural Equipment',   'Agricultural Machinery',   'CNH Industrial N.V.',                      'NYSE',   'NYSE'),
    ('FHN',   'FHN',  'Financial',             'Banking',                  'Regional Banks',           'First Horizon National Corp.',              'NYSE',   'NYSE'),
    ('JBLU',  'JBLU', 'Industrial',            'Airlines',                 'Airlines',                 'JetBlue Airways Corp.',                    'NASDAQ', 'NASDAQ'),
    ('FROG',  'FROG', 'Technology',            'Software',                 'DevOps Platform',          'JFrog Ltd.',                               'NASDAQ', 'NASDAQ'),
    ('RCAT',  'RCAT', 'Technology',            'Drones',                   'Defense Technology',       'Red Cat Holdings Inc.',                    'NASDAQ', 'NASDAQ'),
    ('AR',    'AR',   'Energy',               'Natural Gas',               'Natural Gas E&P',          'Antero Resources Corp.',                   'NYSE',   'NYSE'),
    ('STM',   'STM',  'Technology',            'Semiconductors',           'Semiconductors',           'STMicroelectronics N.V.',                  'NYSE',   'NYSE'),
    ('BAM',   'BAM',  'Financial',             'Asset Management',         'Alternative Asset Mgmt',   'Brookfield Asset Management Ltd.',          'NYSE',   'NYSE'),
    ('SEI',   'SEI',  'Financial',             'Asset Management',         'Financial Technology',     'SEI Investments Company',                  'NASDAQ', 'NASDAQ'),
    ('AMC',   'AMC',  'Consumer Cyclical',     'Entertainment',            'Movie Theaters',           'AMC Entertainment Holdings Inc.',           'NYSE',   'NYSE'),
    ('QUBT',  'QUBT', 'Technology',            'Quantum Computing',        'Quantum Computing',        'Quantum Computing Inc.',                   'NASDAQ', 'NASDAQ'),
    ('RPRX',  'RPRX', 'Healthcare',            'Pharmaceuticals',          'Pharma Royalties',         'Royalty Pharma plc',                       'NASDAQ', 'NASDAQ'),
    ('HRB',   'HRB',  'Consumer Non-cyclical', 'Financial Services',       'Tax Services',             'H&R Block Inc.',                           'NYSE',   'NYSE'),
    ('CNQ',   'CNQ',  'Energy',               'Oil & Gas',                  'Oil Sands E&P',            'Canadian Natural Resources Ltd.',           'NYSE',   'NYSE'),
    ('S',     'S',    'Technology',            'Software',                 'Cybersecurity',            'SentinelOne Inc.',                         'NYSE',   'NYSE'),
    ('DOCU',  'DOCU', 'Technology',            'Software',                 'Document Management',      'DocuSign Inc.',                            'NASDAQ', 'NASDAQ'),
    ('ASX',   'ASX',  'Technology',            'Semiconductors',           'Semiconductor Packaging',  'ASE Technology Holding Co Ltd.',            'NYSE',   'NYSE'),
    ('VOD',   'VOD',  'Communications',        'Telecom',                  'Wireless Telecom',         'Vodafone Group plc',                       'NASDAQ', 'NASDAQ'),
    ('RXRX',  'RXRX', 'Healthcare',            'Biotechnology',            'AI Drug Discovery',        'Recursion Pharmaceuticals Inc.',           'NASDAQ', 'NASDAQ'),
    ('EQH',   'EQH',  'Financial',             'Insurance',                'Financial Services',       'Equitable Holdings Inc.',                  'NYSE',   'NYSE'),
    ('NXE',   'NXE',  'Energy',               'Uranium',                   'Uranium Mining',           'NexGen Energy Ltd.',                       'NYSE',   'NYSE'),
    ('ADT',   'ADT',  'Industrial',            'Security Services',        'Electronic Security',      'ADT Inc.',                                 'NASDAQ', 'NASDAQ'),
    ('AVTR',  'AVTR', 'Healthcare',            'Life Sciences',            'Life Sciences Equipment',  'Avantor Inc.',                             'NYSE',   'NYSE'),
    ('STKL',  'STKL', 'Consumer Non-cyclical', 'Food',                     'Plant-Based Foods',        'SunOpta Inc.',                             'NASDAQ', 'NASDAQ'),
    ('QS',    'QS',   'Technology',            'Battery',                  'EV Battery Technology',    'QuantumScape Corporation',                 'NYSE',   'NYSE'),
    ('UPST',  'UPST', 'Technology',            'Software',                 'AI Lending Platform',      'Upstart Holdings Inc.',                    'NASDAQ', 'NASDAQ'),
    ('BBIO',  'BBIO', 'Healthcare',            'Biotechnology',            'Biotechnology',            'BridgeBio Pharma Inc.',                    'NASDAQ', 'NASDAQ'),
    ('ATI',   'ATI',  'Basic Materials',       'Specialty Materials',      'Specialty Alloys',         'ATI Inc.',                                 'NYSE',   'NYSE'),
    ('SBSW',  'SBSW', 'Basic Materials',       'Precious Metals',          'Platinum/Palladium Mining','Sibanye Stillwater Ltd.',                   'NYSE',   'NYSE'),
    ('ABEV',  'ABEV', 'Consumer Non-cyclical', 'Beverages',                'Beer/Beverages',           'Ambev S.A.',                               'NYSE',   'NYSE'),
    ('JHX',   'JHX',  'Industrial',            'Construction Materials',   'Fiber Cement',             'James Hardie Industries plc',              'NYSE',   'NYSE'),
    ('OBDC',  'OBDC', 'Financial',             'Business Development Co',  'BDC Lending',              'Blue Owl Capital Corporation',              'NYSE',   'NYSE'),
    ('FMC',   'FMC',  'Basic Materials',       'Chemicals',                'Agricultural Chemicals',   'FMC Corporation',                          'NYSE',   'NYSE'),
    ('PSTG',  'PSTG', 'Technology',            'Software',                 'Cloud Storage',            'Pure Storage Inc.',                        'NYSE',   'NYSE'),
    ('AXTI',  'AXTI', 'Technology',            'Semiconductors',           'Compound Semiconductors',  'AXT Inc.',                                 'NASDAQ', 'NASDAQ'),
    ('EXK',   'EXK',  'Basic Materials',       'Silver',                   'Silver Mining',            'Endeavour Silver Corp.',                   'NYSE',   'NYSE'),
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
print(f"✅ ETF file updated: {len(df_new_etf)} new ETFs attempted (total: {len(df_etf)})")

# Stock update
df_stock = pd.read_csv(stock_file)
df_new_stock = pd.DataFrame(stock_additions, columns=['symbol', 'query_symbol', 'industry', 'category', 'subcategory', 'longName', 'exchange', 'primaryExchange'])
df_stock = pd.concat([df_stock, df_new_stock], ignore_index=True)
df_stock.drop_duplicates(subset=['symbol'], keep='first', inplace=True)
df_stock.to_csv(stock_file, index=False)
print(f"✅ Stock file updated: {len(df_new_stock)} new stocks attempted (total: {len(df_stock)})")

print(f"\n📊 Total classified: {len(df_etf)} ETFs + {len(df_stock)} stocks = {len(df_etf) + len(df_stock)}")
