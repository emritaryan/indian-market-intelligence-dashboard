"""Nifty 100 scan logic. All Kite credentials stay in the backend."""
from datetime import datetime, timedelta, timezone
from io import StringIO
import time
from threading import RLock
HISTORY_LOCK = RLock()
import pandas as pd
import requests
from kiteconnect.exceptions import TokenException

CSV_URL = "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"


def constituents():
    response = requests.get(CSV_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    response.raise_for_status()
    data = pd.read_csv(StringIO(response.text))
    data.columns = data.columns.str.strip()
    if not {"Symbol", "Company Name"}.issubset(data.columns):
        raise ValueError("Official constituent CSV has unexpected columns.")
    data["Symbol"] = data["Symbol"].str.strip()
    if len(data) != 100 or data["Symbol"].duplicated().any():
        raise ValueError("Expected 100 unique official constituents.")
    return data.sort_values("Symbol").to_dict("records")


def crossover(candles, symbol, company, short, long, start, end):
    row = {"ticker": symbol, "company": company, "crossover_type": "No crossover",
           "crossover_date": None, "close": None, "short_sma": None, "long_sma": None}
    if not candles:
        row["crossover_type"] = "No data"
        return row
    data = pd.DataFrame(candles).sort_values("date").drop_duplicates("date")
    data["session"] = pd.to_datetime(data["date"]).dt.date
    data = data[data["session"] <= end].copy()
    data["fast"] = data["close"].rolling(short).mean()
    data["slow"] = data["close"].rolling(long).mean()
    if len(data) < long + 1:
        row["crossover_type"] = "Insufficient history"
        return row
    up = (data.fast > data.slow) & (data.fast.shift() <= data.slow.shift())
    down = (data.fast < data.slow) & (data.fast.shift() >= data.slow.shift())
    found = data[(up | down) & (data.session >= start)]
    if not found.empty:
        last = found.iloc[-1]
        row.update(crossover_type="Bullish" if up.loc[last.name] else "Bearish",
                   crossover_date=last.session.isoformat(), close=round(float(last.close), 2),
                   short_sma=round(float(last.fast), 2), long_sma=round(float(last.slow), 2))
    return row


def fetch_candles(kite, token, start, end):
    # Retry transient transport/rate-limit errors, but never retry expired login.
    for attempt in range(3):
        try:
            with HISTORY_LOCK:
                time.sleep(0.5 if attempt == 0 else 2 ** attempt)
                return kite.historical_data(token, start, end, "day")
        except TokenException:
            raise
        except Exception:
            if attempt == 2:
                raise


def scan(kite, settings, update):
    members = constituents()[:settings["max_stocks"]]
    update(total=len(members), message="Mapping NSE equity instruments…")
    instruments = kite.instruments("NSE")
    tokens = {i["tradingsymbol"]: i["instrument_token"] for i in instruments
              if i["exchange"] == "NSE" and i["segment"] == "NSE" and i["instrument_type"] == "EQ"}
    end = datetime.now(timezone(timedelta(hours=5, minutes=30))).date() - timedelta(days=1)
    start = end - timedelta(days=settings["lookback_days"] - 1)
    # Extra history initializes both averages before the selected signal window.
    fetch_start = start - timedelta(days=settings["long_sma"] * 3 + 30)
    rows, warnings = [], []
    for index, member in enumerate(members):
        symbol, company = member["Symbol"], member["Company Name"]
        update(completed=index, message=f"Fetching {symbol}")
        row = crossover([], symbol, company, settings["short_sma"], settings["long_sma"], start, end)
        if symbol not in tokens:
            row["crossover_type"] = "Unmapped"
            warnings.append(f"{symbol}: no NSE equity instrument mapping.")
        else:
            try:
                candles, cursor = [], fetch_start
                while cursor <= end:
                    chunk_end = min(cursor + timedelta(days=364), end)
                    # Keep the scan below Kite's historical API rate limit.
                    candles.extend(fetch_candles(kite, tokens[symbol], cursor, chunk_end))
                    cursor = chunk_end + timedelta(days=1)
                row = crossover(candles, symbol, company, settings["short_sma"], settings["long_sma"], start, end)
                if row["crossover_type"] in {"No data", "Insufficient history"}:
                    warnings.append(f"{symbol}: {row['crossover_type'].lower()}.")
            except TokenException:
                raise
            except Exception:
                row["crossover_type"] = "Fetch failed"
                warnings.append(f"{symbol}: history unavailable; check Kite data subscription or retry.")
        rows.append(row)
        update(completed=index + 1)
    rows.sort(key=lambda row: (-(int(row["crossover_date"].replace("-", ""))) if row["crossover_date"] else 0, row["ticker"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return {"rows": rows, "warnings": warnings, "from_date": start.isoformat(), "to_date": end.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat(), "settings": settings}
