"""Single-stock analytics built from Kite, Yahoo Finance, and official NSE archives."""
import csv
import math
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from threading import RLock

import pandas as pd
import requests
import yfinance as yf
from kiteconnect.exceptions import TokenException

from signals import fetch_candles

IST = timezone(timedelta(hours=5, minutes=30))
ROOT = Path(__file__).resolve().parent.parent
CONSTITUENTS_FILE = ROOT / "nifty100_constituents.csv"
RANGES = {"1M": 45, "3M": 120, "6M": 240, "YTD": 400, "1Y": 400,
          "3Y": 1150, "5Y": 1900, "MAX": 3650}
LOCK = RLock()
CACHE = {}


def cached(key, seconds, loader):
    with LOCK:
        item = CACHE.get(key)
        if item and time.monotonic() - item[0] < seconds:
            return item[1]
    value = loader()
    with LOCK:
        CACHE[key] = (time.monotonic(), value)
    return value


def members():
    data = pd.read_csv(CONSTITUENTS_FILE)
    data.columns = data.columns.str.strip()
    data["Symbol"] = data["Symbol"].astype(str).str.strip()
    return [{"symbol": row["Symbol"], "company": row["Company Name"],
             "sector": row.get("Industry", "Other")} for _, row in data.iterrows()]


def instrument_tokens(kite):
    def load():
        return {item["tradingsymbol"]: item["instrument_token"]
                for item in kite.instruments("NSE")
                if item.get("exchange") == "NSE" and item.get("segment") == "NSE"
                and item.get("instrument_type") == "EQ"}
    return cached("nse-equity-tokens", 6 * 3600, load)


def completed_session_date():
    now = datetime.now(IST)
    if now.weekday() < 5 and now.strftime("%H:%M") >= "15:45":
        return now.date()
    return now.date() - timedelta(days=1)


def candles_for_range(kite, token, range_name):
    range_name = range_name.upper()
    days = RANGES.get(range_name, RANGES["1Y"])
    end = completed_session_date()
    chart_start = datetime(end.year, 1, 1).date() if range_name == "YTD" else end - timedelta(days=days)
    fetch_start = chart_start - timedelta(days=180)

    def load():
        rows, cursor = [], fetch_start
        while cursor <= end:
            chunk_end = min(cursor + timedelta(days=364), end)
            rows.extend(fetch_candles(kite, token, cursor, chunk_end))
            cursor = chunk_end + timedelta(days=1)
        return rows

    raw = cached(f"stock-history:{token}:{range_name}:{end}", 900, load)
    data = pd.DataFrame(raw)
    if data.empty:
        return data, chart_start, end
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values("date").drop_duplicates("date").copy()
    for period in (10, 20, 50, 100):
        data[f"sma{period}"] = data["close"].rolling(period).mean()
    delta = data["close"].diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = gain / loss.replace(0, float("nan"))
    data["rsi14"] = 100 - (100 / (1 + rs))
    data["macd"] = data["close"].ewm(span=12, adjust=False, min_periods=12).mean() - data["close"].ewm(span=26, adjust=False, min_periods=26).mean()
    data["macd_signal"] = data["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    data["macd_histogram"] = data["macd"] - data["macd_signal"]
    previous_close = data["close"].shift(1)
    true_range = pd.concat([(data["high"] - data["low"]),
                            (data["high"] - previous_close).abs(),
                            (data["low"] - previous_close).abs()], axis=1).max(axis=1)
    data["atr14"] = true_range.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    return data, chart_start, end


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def technical_summary(last):
    price = number(last.get("close"))
    rsi = number(last.get("rsi14"))
    sma20, sma50 = number(last.get("sma20")), number(last.get("sma50"))
    if price is not None and rsi is not None and sma20 is not None and sma50 is not None:
        if price > sma20 and price > sma50 and rsi >= 50:
            verdict = "Bullish"
        elif price < sma20 and price < sma50 and rsi < 50:
            verdict = "Bearish"
        else:
            verdict = "Neutral"
    else:
        verdict = "Unavailable"
    macd, macd_signal = number(last.get("macd")), number(last.get("macd_signal"))
    atr = number(last.get("atr14"))
    return {"verdict": verdict, "rsi14": round(rsi, 2) if rsi is not None else None,
            "moving_averages": {str(p): round(number(last.get(f"sma{p}")), 2)
                                if number(last.get(f"sma{p}")) is not None else None
                                for p in (10, 20, 50, 100)},
            "macd": {"line": round(macd, 2) if macd is not None else None,
                     "signal": round(macd_signal, 2) if macd_signal is not None else None,
                     "histogram": round(number(last.get("macd_histogram")), 2)
                     if number(last.get("macd_histogram")) is not None else None,
                     "verdict": "Bullish" if macd is not None and macd_signal is not None and macd > macd_signal else "Bearish"
                     if macd is not None and macd_signal is not None else "Unavailable"},
            "atr14": round(atr, 2) if atr is not None else None,
            "atr_percent": round(atr / price * 100, 2) if atr is not None and price else None,
            "method": "Bullish when close is above SMA 20 and SMA 50 with RSI ≥ 50; bearish when below both with RSI < 50."}


def delivery_history(symbol, end):
    def load():
        rows, cursor, attempts = [], end, 0
        while len(rows) < 7 and attempts < 18:
            attempts += 1
            if cursor.weekday() < 5:
                url = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_" + cursor.strftime("%d%m%Y") + ".csv"
                try:
                    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
                    if response.status_code == 200:
                        for item in csv.DictReader(StringIO(response.text)):
                            clean = {str(k).strip(): str(v).strip() for k, v in item.items() if k is not None}
                            if clean.get("SYMBOL") == symbol and clean.get("SERIES") == "EQ":
                                rows.append({"date": cursor.isoformat(),
                                             "total_volume": int(float(clean.get("TTL_TRD_QNTY") or 0)),
                                             "delivery_volume": int(float(clean.get("DELIV_QTY") or 0)),
                                             "delivery_percent": number(clean.get("DELIV_PER"))})
                                break
                except requests.RequestException:
                    pass
            cursor -= timedelta(days=1)
        return list(reversed(rows))
    return cached(f"delivery:{symbol}:{end}", 1800, load)


FUNDAMENTAL_KEYS = ("market_cap", "stock_pe", "pb_ratio", "industry_pe", "debt_to_equity",
                    "roe", "eps_ttm", "dividend_yield", "book_value", "face_value")


def build_fundamental_metrics(info, kite_price):
    """Combine slow Yahoo company fields with the current Kite market price."""
    price = number(kite_price)
    shares = number(info.get("sharesOutstanding") or info.get("impliedSharesOutstanding"))
    eps = number(info.get("trailingEps"))
    book = number(info.get("bookValue"))
    annual_dividend = number(info.get("trailingAnnualDividendRate") or info.get("dividendRate"))
    debt_percent = number(info.get("debtToEquity"))
    roe_ratio = number(info.get("returnOnEquity"))
    net_income = number(info.get("netIncomeToCommon"))
    book_equity = book * shares if book is not None and shares is not None else None
    if roe_ratio is None and net_income is not None and book_equity and book_equity > 0:
        roe_ratio = net_income / book_equity

    market_cap = price * shares if price is not None and shares is not None else number(info.get("marketCap"))
    stock_pe = price / eps if price is not None and eps is not None and eps > 0 else number(info.get("trailingPE"))
    pb_ratio = price / book if price is not None and book is not None and book > 0 else number(info.get("priceToBook"))
    dividend_yield = annual_dividend / price * 100 if annual_dividend is not None and price else None
    if dividend_yield is None:
        yahoo_yield = number(info.get("trailingAnnualDividendYield"))
        dividend_yield = yahoo_yield * 100 if yahoo_yield is not None else None

    return {"market_cap": market_cap, "stock_pe": stock_pe, "pb_ratio": pb_ratio,
            "industry_pe": None,
            "debt_to_equity": debt_percent / 100 if debt_percent is not None else None,
            "roe": roe_ratio * 100 if roe_ratio is not None else None,
            "eps_ttm": eps, "dividend_yield": dividend_yield,
            "book_value": book, "face_value": None}


def yahoo_fundamentals(symbol, kite_price):
    empty = {key: None for key in FUNDAMENTAL_KEYS}

    def load():
        payload = yf.Ticker(f"{symbol}.NS").get_info()
        if not isinstance(payload, dict) or not payload:
            raise ValueError("Yahoo Finance returned no company information.")
        return payload

    try:
        info = cached(f"yahoo-info:{symbol}", 12 * 3600, load)
        metrics = build_fundamental_metrics(info, kite_price)
        available = any(value is not None for value in metrics.values())
        return {"metrics": metrics, "source": "Yahoo Finance via yfinance + Zerodha Kite LTP",
                "status": "available" if available else "unavailable",
                "industry": info.get("industry"),
                "message": "P/E, P/B, market cap and dividend yield use the current Kite price when their Yahoo inputs are available. ROE falls back to TTM net income ÷ book equity. Industry P/E and face value are not supplied reliably by either source."}
    except Exception:
        return {"metrics": empty, "source": "Yahoo Finance via yfinance + Zerodha Kite LTP",
                "status": "unavailable", "industry": None,
                "message": "Yahoo fundamentals are temporarily unavailable for this company. Price and technical data remain available from Kite."}


def stock_data(kite, symbol, range_name="1Y"):
    symbol = symbol.upper().strip()
    member = next((item for item in members() if item["symbol"] == symbol), None)
    if not member:
        raise ValueError("Choose a stock from the Nifty 100 list.")
    token = instrument_tokens(kite).get(symbol)
    if not token:
        raise ValueError("This Nifty 100 symbol is not mapped in Kite's NSE instrument list.")
    data, chart_start, end = candles_for_range(kite, token, range_name)
    if data.empty:
        raise ValueError("Kite returned no historical candles for this stock.")
    quote = kite.quote([f"NSE:{symbol}"]).get(f"NSE:{symbol}", {})
    values = chart_rows(data, chart_start)
    last = data.iloc[-1].to_dict()
    previous = quote.get("ohlc", {}).get("close")
    price = quote.get("last_price") or last.get("close")
    move = (price / previous - 1) * 100 if price is not None and previous else None
    return {"stock": member, "range": range_name.upper(), "series": values,
            "quote": {"price": number(price), "change": number(move), "ohlc": quote.get("ohlc", {}),
                      "timestamp": (quote.get("timestamp") or quote.get("last_trade_time")).isoformat()
                      if quote.get("timestamp") or quote.get("last_trade_time") else None},
            "technical": technical_summary(last), "delivery": delivery_history(symbol, end),
            "fundamentals": yahoo_fundamentals(symbol, price),
            "sources": {"price": "Zerodha Kite", "delivery": "NSE security-wise price volume archive",
                        "fundamentals": "Yahoo Finance via yfinance, calculated with Kite LTP"}}


def ipo_data():
    def load():
        url = "https://www.nseindia.com/api/ipo-current-issue"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json",
                            "Referer": "https://www.nseindia.com/market-data/all-upcoming-issues-ipo"}, timeout=20)
        response.raise_for_status()
        return [{"company": row.get("companyName"), "symbol": row.get("symbol"),
                 "open_date": row.get("issueStartDate"), "close_date": row.get("issueEndDate"),
                 "price_band": row.get("issuePrice"), "status": row.get("status")}
                for row in response.json() if row.get("status") == "Active"]
    try:
        return {"items": cached("nse-current-ipos", 900, load), "source": "NSE current issues"}
    except Exception:
        return {"items": [], "source": "NSE current issues", "error": "Current IPO feed is temporarily unavailable."}


def chart_rows(data, chart_start):
    chart = data[data["date"].dt.date >= chart_start].copy()
    values = []
    for row in chart.itertuples():
        values.append({"date": row.date.date().isoformat(), "open": number(row.open), "high": number(row.high),
                       "low": number(row.low), "close": number(row.close), "volume": int(row.volume or 0),
                       **{f"sma{p}": number(getattr(row, f"sma{p}")) for p in (10, 20, 50, 100)}})
    return values


def stock_chart_data(kite, symbol, range_name="1Y"):
    symbol = symbol.upper().strip()
    member = next((item for item in members() if item["symbol"] == symbol), None)
    if not member:
        raise ValueError("Choose a stock from the Nifty 100 list.")
    token = instrument_tokens(kite).get(symbol)
    if not token:
        raise ValueError("This Nifty 100 symbol is not mapped in Kite's NSE instrument list.")
    data, chart_start, _ = candles_for_range(kite, token, range_name)
    if data.empty:
        raise ValueError("Kite returned no historical candles for this stock.")
    return {"symbol": symbol, "range": range_name.upper(), "series": chart_rows(data, chart_start)}
