#!/usr/bin/env python3
"""Add Batch 5 sector classifications — top unnamed from Feb 2-6 2026 weekly report"""
import pandas as pd

# ── ETFs (ticker, sector, subsector, leverage, direction, description) ──────────
etf_additions = [
    ('SPXL',  'Equity',        'Large Cap',              '3x',   'Long',  'Direxion Daily S&P 500 Bull 3X Shares'),
    ('SPYG',  'Equity',        'Large Cap Growth',       'None', 'Long',  'SPDR Portfolio S&P 500 Growth ETF'),
    ('SH',    'Equity',        'Large Cap Inverse',      '1x',   'Short', 'ProShares Short S&P500'),
    ('SDS',   'Equity',        'Large Cap Inverse',      '2x',   'Short', 'ProShares UltraShort S&P500'),
    ('UDOW',  'Equity',        'Dow Jones',              '3x',   'Long',  'ProShares UltraPro Dow30'),
    ('SHYG',  'Fixed Income',  'Short-Term High Yield',  'None', 'Long',  'iShares 0-5 Year High Yield Corporate Bond ETF'),
    ('SJNK',  'Fixed Income',  'Short-Term High Yield',  'None', 'Long',  'SPDR Bloomberg Short Term High Yield Bond ETF'),
    ('XHB',   'Equity',        'Homebuilders',           'None', 'Long',  'SPDR S&P Homebuilders ETF'),
    ('QYLD',  'Equity',        'Covered Call',           'None', 'Long',  'Global X NASDAQ 100 Covered Call ETF'),
    ('SCHH',  'Equity',        'REITs',                  'None', 'Long',  'Schwab US REIT ETF'),
    ('VXX',   'Volatility',    'VIX Futures',            'None', 'Long',  'iPath Series B S&P 500 VIX ST Futures ETN'),
    ('ILF',   'Equity',        'Latin America',          'None', 'Long',  'iShares Latin America 40 ETF'),
    ('EFV',   'Equity',        'International Value',    'None', 'Long',  'iShares MSCI EAFE Value ETF'),
    ('ISVL',  'Equity',        'International Value',    'None', 'Long',  'iShares MSCI Intl Value Factor ETF'),
    ('TMF',   'Fixed Income',  'Long Treasury',          '3x',   'Long',  'Direxion Daily 20+ Yr Treasury Bull 3X Shares'),
    ('SPTL',  'Fixed Income',  'Long Treasury',          'None', 'Long',  'SPDR Portfolio Long Term Treasury ETF'),
    ('IBB',   'Healthcare',    'Biotechnology',          'None', 'Long',  'iShares Biotechnology ETF'),
    ('MSTU',  'Equity',        'MicroStrategy Bull',     '2x',   'Long',  'T-Rex 2X Long MSTR Daily Target ETF'),
    ('MSTZ',  'Equity',        'MicroStrategy Bear',     '2x',   'Short', 'T-Rex 2X Inverse MSTR Daily Target ETF'),
    ('TSLZ',  'Equity',        'Tesla Bull',             '2x',   'Long',  'T-Rex 2X Long Tesla Daily Target ETF'),
    ('TSDD',  'Equity',        'Tesla Bear',             '2x',   'Short', 'GraniteShares 2x Short Tesla Daily ETP'),
    ('AMDL',  'Equity',        'AMD Bull',               '2x',   'Long',  'GraniteShares 2x Long AMD Daily ETP'),
    ('SBIT',  'Equity',        'Bitcoin Inverse',        '1x',   'Short', 'ProShares Short Bitcoin ETF'),
    ('BTC',   'Equity',        'Bitcoin',                'None', 'Long',  'Grayscale Bitcoin Mini Trust ETF'),
    ('PBUS',  'Fixed Income',  'Aggregate Bond',         'None', 'Long',  'Invesco PureBeta US Aggregate Bond ETF'),
    ('GCOW',  'Equity',        'Global Dividend',        'None', 'Long',  'Pacer Global Cash Cows Dividend ETF'),
]

# ── Stocks (symbol, query_symbol, industry, category, subcategory, longName, exchange, primaryExchange)
# Note: industry → sector, category → subsector, subcategory → detailed industry in the weekly report
stock_additions = [
    ('SPOT',  'SPOT',  'Technology',            'Entertainment',            'Music Streaming',          'Spotify Technology S.A.',                  'NYSE',   'NYSE'),
    ('WBS',   'WBS',   'Financial',             'Banking',                  'Commercial Banks',         'Webster Financial Corporation',             'NASDAQ', 'NASDAQ'),
    ('NVS',   'NVS',   'Healthcare',            'Pharmaceuticals',          'Pharmaceuticals',          'Novartis AG',                              'NYSE',   'NYSE'),
    ('PFGC',  'PFGC',  'Consumer Non-cyclical', 'Food',                     'Food Distribution',        'Performance Food Group Company',           'NASDAQ', 'NASDAQ'),
    ('CWAN',  'CWAN',  'Technology',            'Software',                 'Financial Software',       'Clearwater Analytics Holdings Inc.',       'NYSE',   'NYSE'),
    ('CFLT',  'CFLT',  'Technology',            'Software',                 'Data Infrastructure',      'Confluent Inc.',                           'NASDAQ', 'NASDAQ'),
    ('SAN',   'SAN',   'Financial',             'Banking',                  'International Banks',      'Banco Santander S.A.',                     'NYSE',   'NYSE'),
    ('RRX',   'RRX',   'Industrial',            'Diversified Industrials',  'Diversified Industrials',  'Roper Technologies Inc.',                  'NASDAQ', 'NASDAQ'),
    ('BILL',  'BILL',  'Technology',            'Software',                 'Financial Software',       'Bill Holdings Inc.',                       'NYSE',   'NYSE'),
    ('VEEV',  'VEEV',  'Healthcare',            'Software',                 'Healthcare IT',            'Veeva Systems Inc.',                       'NYSE',   'NYSE'),
    ('SLAB',  'SLAB',  'Technology',            'Semiconductors',           'Semiconductors',           'Silicon Laboratories Inc.',                'NASDAQ', 'NASDAQ'),
    ('ENTG',  'ENTG',  'Technology',            'Semiconductors',           'Semiconductor Equipment',  'Entegris Inc.',                            'NASDAQ', 'NASDAQ'),
    ('FLEX',  'FLEX',  'Technology',            'Electronics',              'Contract Manufacturing',   'Flex Ltd.',                                'NASDAQ', 'NASDAQ'),
    ('IOT',   'IOT',   'Technology',            'Software',                 'IoT Platform Software',    'Samsara Inc.',                             'NYSE',   'NYSE'),
    ('NYT',   'NYT',   'Communications',        'Media',                    'Digital Media',            'The New York Times Company',               'NYSE',   'NYSE'),
    ('USFD',  'USFD',  'Consumer Non-cyclical', 'Food',                     'Food Distribution',        'US Foods Holding Corp.',                   'NYSE',   'NYSE'),
    ('TPG',   'TPG',   'Financial',             'Investment Managers',      'Private Equity',           'TPG Inc.',                                 'NASDAQ', 'NASDAQ'),
    ('Z',     'Z',     'Technology',            'Real Estate',              'Online Real Estate',       'Zillow Group Inc.',                        'NASDAQ', 'NASDAQ'),
    ('TRI',   'TRI',   'Communications',        'Information Services',     'Professional Information',  'Thomson Reuters Corporation',             'NYSE',   'NYSE'),
    ('TRU',   'TRU',   'Technology',            'Data Analytics',           'Consumer Data Analytics',  'TransUnion',                               'NYSE',   'NYSE'),
    ('SSNC',  'SSNC',  'Technology',            'Software',                 'Financial Software',       'SS&C Technologies Holdings Inc.',          'NASDAQ', 'NASDAQ'),
    ('DUOL',  'DUOL',  'Technology',            'Software',                 'Education Software',       'Duolingo Inc.',                            'NASDAQ', 'NASDAQ'),
    ('SNY',   'SNY',   'Healthcare',            'Pharmaceuticals',          'Pharmaceuticals',          'Sanofi S.A.',                              'NASDAQ', 'NASDAQ'),
    ('STLA',  'STLA',  'Consumer Cyclical',     'Automotive',               'Auto Manufacturers',       'Stellantis N.V.',                          'NYSE',   'NYSE'),
    ('CRH',   'CRH',  'Industrial',             'Construction Materials',   'Construction Materials',   'CRH plc',                                  'NYSE',   'NYSE'),
    ('DT',    'DT',    'Technology',            'Software',                 'Observability Software',   'Dynatrace Inc.',                           'NYSE',   'NYSE'),
    ('JD',    'JD',    'Consumer Cyclical',     'Internet Retail',          'Internet Retail',          'JD.com Inc.',                              'NASDAQ', 'NASDAQ'),
    ('DOCS',  'DOCS',  'Healthcare',            'Software',                 'Healthcare IT',            'Doximity Inc.',                            'NYSE',   'NYSE'),
    ('ONON',  'ONON',  'Consumer Cyclical',     'Footwear',                 'Athletic Footwear',        'On Holding AG',                            'NYSE',   'NYSE'),
    ('TSEM',  'TSEM',  'Technology',            'Semiconductors',           'Semiconductor Foundry',    'Tower Semiconductor Ltd.',                 'NASDAQ', 'NASDAQ'),
    ('SIRI',  'SIRI',  'Communications',        'Broadcasting',             'Satellite Radio',          'SiriusXM Holdings Inc.',                   'NASDAQ', 'NASDAQ'),
    ('FOLD',  'FOLD',  'Healthcare',            'Biotechnology',            'Biotechnology',            'Amicus Therapeutics Inc.',                 'NASDAQ', 'NASDAQ'),
    ('NVT',   'NVT',   'Industrial',            'Electrical Equipment',     'Electrical Equipment',     'nVent Electric plc',                       'NYSE',   'NYSE'),
    ('VRNS',  'VRNS',  'Technology',            'Software',                 'Data Security Software',   'Varonis Systems Inc.',                     'NASDAQ', 'NASDAQ'),
    ('TECK',  'TECK',  'Basic Materials',       'Mining',                   'Diversified Mining',       'Teck Resources Ltd.',                      'NYSE',   'NYSE'),
    ('LBRT',  'LBRT',  'Energy',               'Oil Services',              'Oilfield Services',        'Liberty Energy Inc.',                      'NYSE',   'NYSE'),
    ('TWLO',  'TWLO',  'Technology',            'Software',                 'Communications Software',  'Twilio Inc.',                              'NYSE',   'NYSE'),
    ('ARMK',  'ARMK',  'Consumer Non-cyclical', 'Food Services',            'Managed Services',         'Aramark Holdings Corp.',                   'NASDAQ', 'NASDAQ'),
    ('GRAB',  'GRAB',  'Technology',            'Internet',                 'Ride Sharing/Delivery',    'Grab Holdings Ltd.',                       'NASDAQ', 'NASDAQ'),
    ('NVTS',  'NVTS',  'Technology',            'Semiconductors',           'Power Semiconductors',     'Navitas Semiconductor Corp.',              'NASDAQ', 'NASDAQ'),
    ('PCOR',  'PCOR',  'Technology',            'Software',                 'Construction Software',    'Procore Technologies Inc.',                'NYSE',   'NYSE'),
    ('CLF',   'CLF',   'Basic Materials',       'Steel',                    'Steel Manufacturing',      'Cleveland-Cliffs Inc.',                    'NYSE',   'NYSE'),
    ('HDB',   'HDB',   'Financial',             'Banking',                  'International Banks',      'HDFC Bank Ltd.',                           'NYSE',   'NYSE'),
    ('ZETA',  'ZETA',  'Technology',            'Software',                 'Marketing Technology',     'Zeta Global Holdings Corp.',               'NYSE',   'NYSE'),
    ('GH',    'GH',    'Healthcare',            'Diagnostics',              'Liquid Biopsy',            'Guardant Health Inc.',                     'NASDAQ', 'NASDAQ'),
    ('HUBS',  'HUBS',  'Technology',            'Software',                 'CRM Software',             'HubSpot Inc.',                             'NYSE',   'NYSE'),
    ('RIG',   'RIG',   'Energy',               'Offshore Drilling',         'Offshore Drilling',        'Transocean Ltd.',                          'NYSE',   'NYSE'),
    ('NTNX',  'NTNX',  'Technology',            'Software',                 'Cloud Infrastructure',     'Nutanix Inc.',                             'NASDAQ', 'NASDAQ'),
    ('ARCC',  'ARCC',  'Financial',             'Business Development Co',  'BDC Lending',              'Ares Capital Corporation',                 'NASDAQ', 'NASDAQ'),
    ('LUMN',  'LUMN',  'Communications',        'Telecom',                  'Fiber Network Telecom',    'Lumen Technologies Inc.',                  'NYSE',   'NYSE'),
    ('SONY',  'SONY',  'Technology',            'Consumer Electronics',     'Consumer Electronics',     'Sony Group Corporation',                   'NYSE',   'NYSE'),
    ('MNDY',  'MNDY',  'Technology',            'Software',                 'Work Management Software', 'Monday.com Ltd.',                          'NASDAQ', 'NASDAQ'),
    ('ZS',    'ZS',    'Technology',            'Software',                 'Cybersecurity',            'Zscaler Inc.',                             'NASDAQ', 'NASDAQ'),
    ('MMYT',  'MMYT',  'Consumer Cyclical',     'Travel',                   'Online Travel Services',   'MakeMyTrip Ltd.',                          'NASDAQ', 'NASDAQ'),
    ('GPK',   'GPK',   'Industrial',            'Packaging',                'Paperboard Packaging',     'Graphic Packaging Holding Company',        'NYSE',   'NYSE'),
    ('AMKR',  'AMKR',  'Technology',            'Semiconductors',           'Semiconductor Packaging',  'Amkor Technology Inc.',                    'NASDAQ', 'NASDAQ'),
    ('AS',    'AS',    'Consumer Cyclical',     'Sporting Goods',            'Athletic Equipment',       'Amer Sports Inc.',                         'NYSE',   'NYSE'),
    ('CORZ',  'CORZ',  'Technology',            'Bitcoin Mining',           'Cryptocurrency Mining',    'Core Scientific Inc.',                     'NASDAQ', 'NASDAQ'),
    ('RUN',   'RUN',   'Energy',               'Solar',                     'Residential Solar',        'Sunrun Inc.',                              'NASDAQ', 'NASDAQ'),
    ('SYM',   'SYM',   'Technology',            'Robotics',                 'Warehouse Automation',     'Symbotic Inc.',                            'NASDAQ', 'NASDAQ'),
    ('SM',    'SM',    'Energy',               'Oil & Gas',                  'Oil & Gas Exploration',    'SM Energy Company',                        'NYSE',   'NYSE'),
    ('EQX',   'EQX',   'Basic Materials',       'Gold',                     'Gold Mining',              'Equinox Gold Corp.',                       'NYSE',   'NYSE'),
    ('AGI',   'AGI',   'Basic Materials',       'Gold',                     'Gold Mining',              'Alamos Gold Inc.',                         'NYSE',   'NYSE'),
    ('COMP',  'COMP',  'Technology',            'Real Estate',              'Online Real Estate Broker', 'Compass Inc.',                            'NYSE',   'NYSE'),
    ('FTI',   'FTI',   'Energy',               'Oil Services',              'Subsea Technologies',      'TechnipFMC plc',                           'NYSE',   'NYSE'),
    ('GTLB',  'GTLB',  'Technology',            'Software',                 'DevOps Platform',          'GitLab Inc.',                              'NASDAQ', 'NASDAQ'),
    ('LUNR',  'LUNR',  'Technology',            'Space',                    'Space Exploration',        'Intuitive Machines Inc.',                  'NASDAQ', 'NASDAQ'),
    ('UAMY',  'UAMY',  'Basic Materials',       'Mining',                   'Specialty Metals',         'United States Antimony Corp.',             'NYSE',   'NYSE'),
    ('ELF',   'ELF',   'Consumer Non-cyclical', 'Beauty',                   'Beauty Products',          'e.l.f. Beauty Inc.',                       'NYSE',   'NYSE'),
    ('GGB',   'GGB',   'Basic Materials',       'Steel',                    'Steel Manufacturing',      'Gerdau S.A.',                              'NYSE',   'NYSE'),
    ('RELX',  'RELX',  'Communications',        'Information Services',     'Professional Publishing',  'RELX plc',                                 'NYSE',   'NYSE'),
    ('SMX',   'SMX',   'Technology',            'Software',                 'Blockchain Authentication', 'Security Matters Ltd.',                   'NASDAQ', 'NASDAQ'),
    ('ILMN',  'ILMN',  'Healthcare',            'Life Sciences',            'Genomics',                 'Illumina Inc.',                            'NASDAQ', 'NASDAQ'),
    ('ROIV',  'ROIV',  'Healthcare',            'Biotechnology',            'Biopharmaceuticals',       'Roivant Sciences Ltd.',                    'NASDAQ', 'NASDAQ'),
    ('AMPX',  'AMPX',  'Technology',            'Energy Storage',           'Battery Technology',       'Amprius Technologies Inc.',                'NYSE',   'NYSE'),
    ('VEEV',  'VEEV',  'Healthcare',            'Software',                 'Healthcare IT',            'Veeva Systems Inc.',                       'NYSE',   'NYSE'),
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
