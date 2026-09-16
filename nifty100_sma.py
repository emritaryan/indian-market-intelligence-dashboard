"""Nifty 100 SMA scanner. Run: python nifty100_sma.py

Third-party packages: kiteconnect, pandas, requests.
Credentials: credentials.txt beside this script, with api_key=... and
api_secret_key=... (api_secret also works). Never commit this file.
Paste a fresh Kite request token at the prompt after authorizing the login URL.
The token is exchanged in memory; no access token is written to disk.
Output prices and averages refer to the crossover session, not today's quote.
Current constituents are used; this is not a historical-membership backtest.
"""

from datetime import datetime, timedelta, timezone
from getpass import getpass
from io import StringIO
from pathlib import Path
import os
import time

import pandas as pd
import requests
from kiteconnect import KiteConnect

FOLDER = Path(__file__).resolve().parent
CONSTITUENTS_URL = 'https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv'
COLUMNS = ['Rank', 'Symbol', 'Company', 'Signal Type', 'Crossover Date',
           'Close', 'SMA 6', 'SMA 30']


def read_credentials():
    values = {}
    for line in (FOLDER / 'credentials.txt').read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        separator = '=' if '=' in line else ':'
        if separator in line:
            key, value = line.split(separator, 1)
            values[key.strip().lower().replace(' ', '_')] = value.strip().strip('\"\'')
    key = values.get('api_key')
    secret = values.get('api_secret_key') or values.get('api_secret')
    if not key or not secret:
        raise ValueError('credentials.txt needs api_key and api_secret_key entries.')
    return key, secret


def download_constituents():
    # Official Nifty Indices constituent download; market prices come from Kite.
    response = requests.get(CONSTITUENTS_URL, timeout=45,
                            headers={'User-Agent': 'Mozilla/5.0'})
    response.raise_for_status()
    members = pd.read_csv(StringIO(response.text))
    members.columns = members.columns.str.strip()
    if not {'Symbol', 'Company Name'}.issubset(members.columns):
        raise ValueError('The constituent download did not contain the expected CSV columns.')
    members['Symbol'] = members['Symbol'].str.strip()
    if len(members) != 100 or members['Symbol'].duplicated().any():
        raise ValueError('Expected exactly 100 unique Nifty 100 constituents.')
    members.to_csv(FOLDER / 'nifty100_constituents.csv', index=False)
    return members


def latest_crossover(candles, symbol, company):
    result = {'Symbol': symbol, 'Company': company, 'Signal Type': 'No crossover',
              'Crossover Date': pd.NaT, 'Close': None, 'SMA 6': None, 'SMA 30': None}
    if not candles:
        result['Signal Type'] = 'No data'
        return result
    history = pd.DataFrame(candles).sort_values('date').drop_duplicates('date')
    history['SMA 6'] = history['close'].rolling(6).mean()
    history['SMA 30'] = history['close'].rolling(30).mean()
    if len(history) < 31:
        result['Signal Type'] = 'Insufficient history'
        return result
    # Compare yesterday's relationship with today's relationship.
    bullish = ((history['SMA 6'] > history['SMA 30']) &
               (history['SMA 6'].shift(1) <= history['SMA 30'].shift(1)))
    bearish = ((history['SMA 6'] < history['SMA 30']) &
               (history['SMA 6'].shift(1) >= history['SMA 30'].shift(1)))
    crosses = history.loc[bullish | bearish]
    if not crosses.empty:
        row = crosses.iloc[-1]
        result.update({'Signal Type': 'Bullish' if bullish.loc[row.name] else 'Bearish',
                       'Crossover Date': pd.Timestamp(row['date']).tz_localize(None).normalize(),
                       'Close': row['close'], 'SMA 6': row['SMA 6'], 'SMA 30': row['SMA 30']})
    return result


def main():
    api_key, api_secret = read_credentials()
    kite = KiteConnect(api_key=api_key, timeout=30)
    print('Authorize this URL if you need a fresh request token:')
    print(kite.login_url())
    token = os.environ.pop('KITE_REQUEST_TOKEN', '') or getpass('Fresh request token (hidden): ')
    try:
        session = kite.generate_session(token.strip(), api_secret=api_secret)
        kite.set_access_token(session['access_token'])
    except Exception as error:
        # Avoid logging authentication responses or secrets.
        raise RuntimeError('Kite login failed (' + type(error).__name__ +
                           '). Authorize again and use a fresh request token with the current secret.') from None

    members = download_constituents()
    # Match official NSE cash-equity symbols to Kite instrument tokens.
    instruments = pd.DataFrame(kite.instruments('NSE'))
    equities = instruments[(instruments['exchange'] == 'NSE') &
                           (instruments['segment'] == 'NSE') &
                           (instruments['instrument_type'] == 'EQ')]
    if equities['tradingsymbol'].duplicated().any():
        raise ValueError('Duplicate NSE equity symbols in the instrument list.')
    tokens = equities.set_index('tradingsymbol')['instrument_token'].to_dict()

    # Exclude today to avoid incomplete daily candles, including during market hours.
    today_ist = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    end = today_ist - timedelta(days=1)
    start = end - timedelta(days=730)
    print(f'Scanning completed daily candles from {start} through {end}.')
    rows = []
    failures = []
    for number, member in enumerate(members.to_dict('records'), 1):
        symbol, company = member['Symbol'], member['Company Name']
        print(f'{number:3}/100 {symbol}')
        if symbol not in tokens:
            row = latest_crossover([], symbol, company)
            row['Signal Type'] = 'Unmapped symbol'
            failures.append(symbol)
        else:
            try:
                candles = []
                cursor = start
                # Bounded requests accommodate Kite's daily-history request limit.
                while cursor <= end:
                    chunk_end = min(cursor + timedelta(days=364), end)
                    candles.extend(kite.historical_data(int(tokens[symbol]), cursor, chunk_end, 'day'))
                    time.sleep(0.4)  # Stay below three historical requests per second.
                    cursor = chunk_end + timedelta(days=1)
                row = latest_crossover(candles, symbol, company)
            except Exception as error:
                row = latest_crossover([], symbol, company)
                row['Signal Type'] = 'Fetch failed'
                failures.append(symbol)
                print(f'  Fetch failed ({type(error).__name__}); no signal fabricated.')
        rows.append(row)

    results = pd.DataFrame(rows).sort_values(
        ['Crossover Date', 'Symbol'], ascending=[False, True], na_position='last').reset_index(drop=True)
    results.insert(0, 'Rank', range(1, len(results) + 1))
    results = results[COLUMNS]
    results[['Close', 'SMA 6', 'SMA 30']] = results[['Close', 'SMA 6', 'SMA 30']].round(2)
    output = FOLDER / 'nifty100sma_signals.csv'
    results.to_csv(output, index=False, date_format='%Y-%m-%d')
    print('\n', results.to_string(index=False), sep='')
    print(f'\nSaved: {output}')
    if failures:
        print('INCOMPLETE: check these symbols:', ', '.join(failures))
    return results  # A pandas DataFrame, also usable from an interactive Python session.


if __name__ == '__main__':
    try:
        results = main()
    except Exception as error:
        print(f'Cannot finish: {error}')
        raise SystemExit(1)
