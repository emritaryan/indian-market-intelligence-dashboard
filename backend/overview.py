"""Overview market data: Kite quotes/history and delayed Yahoo macro charts."""
import csv
import json
import math
import time
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from threading import RLock
from urllib.parse import quote
import pandas as pd
import requests
from kiteconnect.exceptions import TokenException
from signals import fetch_candles
from stock import completed_session_date, members

IST = timezone(timedelta(hours=5, minutes=30))
CONFIG = Path(__file__).resolve().parent.parent / "config"
CACHE = {}
CACHE_LOCK = RLock()
KEY_LOCKS = {}


def config():
    return json.loads((CONFIG / "dashboard.json").read_text(encoding="utf-8"))


def cached(key, seconds, loader):
    with CACHE_LOCK:
        lock = KEY_LOCKS.setdefault(key, RLock())
    with lock:
        item = CACHE.get(key)
        if item and time.monotonic() - item[0] < seconds:
            return item[1]
        value = loader()
        CACHE[key] = (time.monotonic(), value)
        return value


def market_status(now=None):
    now = now or datetime.now(IST)
    now = now.astimezone(IST)
    calendar = json.loads((CONFIG / "holidays.json").read_text(encoding="utf-8"))
    today, clock = now.date().isoformat(), now.strftime("%H:%M")
    label, opened = "Market Closed", False
    if now.year != calendar["year"]:
        label = "Calendar needs update"
    elif today in calendar.get("special_sessions", {}):
        special = calendar["special_sessions"][today]
        if special.get("open") and special.get("close"):
            opened = special["open"] <= clock < special["close"]
            label = special["name"] + (" · Open" if opened else " · Closed")
        else:
            label = special["name"] + " · schedule not configured"
    elif today in calendar["holidays"]:
        label = "Holiday: " + calendar["holidays"][today]
    elif now.weekday() < 5 and "09:15" <= clock < "15:30":
        label, opened = "Market Open", True
    return {"label": label, "is_open": opened, "ist_time": now.isoformat(), "hours": "09:15–15:30 IST"}


def change(price, previous):
    return round((price / previous - 1) * 100, 2) if price is not None and previous else None


def valid_kite_timestamp(item):
    """Discard Kite's 1970 sentinel and use the real last-trade time when present."""
    for value in (item.get("timestamp"), item.get("last_trade_time")):
        if not value:
            continue
        try:
            stamp = pd.Timestamp(value).to_pydatetime()
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=IST)
            if stamp.year >= 2000:
                return stamp
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def completed_equity_snapshot(symbols, on_date):
    """Load the latest official NSE equity session once for all Overview stocks."""
    wanted = set(symbols)

    def load():
        cursor = on_date
        for _ in range(12):
            if cursor.weekday() < 5:
                url = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_" + cursor.strftime("%d%m%Y") + ".csv"
                try:
                    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
                    if response.status_code == 200:
                        rows = {}
                        for item in csv.DictReader(StringIO(response.text)):
                            clean = {str(key).strip(): str(value).strip() for key, value in item.items() if key is not None}
                            symbol = clean.get("SYMBOL")
                            if symbol not in wanted or clean.get("SERIES") != "EQ":
                                continue
                            try:
                                price = float(clean["CLOSE_PRICE"])
                                previous = float(clean["PREV_CLOSE"])
                                volume = int(float(clean.get("TTL_TRD_QNTY") or 0))
                                turnover = float(clean.get("TURNOVER_LACS") or 0) * 100000
                                session = datetime.strptime(clean["DATE1"], "%d-%b-%Y").replace(hour=15, minute=30, tzinfo=IST)
                                ohlc = {"open": float(clean["OPEN_PRICE"]), "high": float(clean["HIGH_PRICE"]),
                                        "low": float(clean["LOW_PRICE"]), "close": previous}
                            except (KeyError, TypeError, ValueError):
                                continue
                            rows[symbol] = {"price": price, "change": change(price, previous),
                                "timestamp": session.isoformat(), "stale": True, "volume": volume, "ohlc": ohlc,
                                "absolute_change": round(price - previous, 2),
                                "traded_value": round(turnover if turnover else price * volume, 2)}
                        if rows:
                            return rows
                except requests.RequestException:
                    pass
            cursor -= timedelta(days=1)
        return {}

    return cached("nse-overview-session:" + on_date.isoformat() + ":" + ",".join(sorted(wanted)), 1800, load)


def quote_data(kite):
    settings = config()
    universe = members()
    symbols = ["NSE:" + item["symbol"] for item in settings["indices"]]
    symbols += ["NSE:" + item["symbol"] for item in universe]
    symbols = list(dict.fromkeys(symbols))
    def load():
        # Kite quote endpoint: latest available exchange prices; never scraped NSE prices.
        raw = kite.quote(symbols)
        rows = {}
        now = datetime.now(IST)
        status = market_status(now)
        completed = completed_equity_snapshot([item["symbol"] for item in universe], now.date()) if not status["is_open"] else {}
        for symbol in symbols:
            plain_symbol = symbol[4:]
            if plain_symbol in completed:
                rows[plain_symbol] = completed[plain_symbol]
                continue
            item = raw.get(symbol)
            if not item:
                rows[plain_symbol] = {"price": None, "change": None, "timestamp": None, "stale": True}
                continue
            stamp = valid_kite_timestamp(item)
            price, previous = item.get("last_price"), item.get("ohlc", {}).get("close")
            rows[plain_symbol] = {"price": price, "change": change(price,previous),
                "timestamp": stamp.isoformat() if stamp else None,
                "stale": not stamp or (now-stamp).total_seconds()>120,
                "volume": item.get("volume", 0), "ohlc": item.get("ohlc", {}),
                "absolute_change": round(price-previous, 2) if price is not None and previous else None,
                "traded_value": round((price or 0) * (item.get("volume") or 0), 2)}
        return {"quotes":rows,"universe":universe,"fetched_at":now.isoformat(),"source":"Zerodha Kite"}
    data = cached("quotes:"+json.dumps(symbols),10,load)
    return {**data,"market":market_status(),"config":settings}


def history_data(kite):
    settings = config()
    index_items = settings.get("indices") or [{"symbol": "NIFTY 50", "name": "Nifty 50"}]
    def load():
        raw = kite.instruments("NSE")
        tokens = {i["tradingsymbol"]:i["instrument_token"] for i in raw if i["segment"] in {"NSE","INDICES"}}
        end = completed_session_date()
        index_history, warnings = {}, []
        for item in index_items:
            symbol = item["symbol"]
            try:
                if symbol not in tokens:
                    raise ValueError("Unmapped instrument")
                days = 1900 if symbol == "NIFTY 50" else 120
                candles, cursor = [], end-timedelta(days=days)
                while cursor <= end:
                    chunk_end = min(cursor + timedelta(days=364), end)
                    candles.extend(fetch_candles(kite,tokens[symbol],cursor,chunk_end))
                    cursor = chunk_end + timedelta(days=1)
                data=pd.DataFrame(candles)
                if data.empty: raise ValueError("No history")
                data["date"]=pd.to_datetime(data["date"]).dt.date
                data=data.sort_values("date").drop_duplicates("date")
                data=data[data.date <= end]
                entries=[]
                for r in data.itertuples():
                    point={"date":r.date.isoformat(),"close":float(r.close)}
                    for field in ("open","high","low"):
                        if hasattr(r,field): point[field]=float(getattr(r,field))
                    if hasattr(r,"volume"): point["volume"]=int(r.volume or 0)
                    entries.append(point)
                index_history[symbol]=entries
            except TokenException: raise
            except Exception: warnings.append(symbol+": historical chart unavailable.")
        for item in settings.get("watchlist", []):
            if item["symbol"] not in tokens:
                warnings.append(item["symbol"] + ": historical chart unavailable.")
        nifty=index_history.get("NIFTY 50",[])
        one_year=nifty[-260:]
        stats={"high_52w":max((p.get("high") for p in one_year if p.get("high") is not None),default=None),
               "low_52w":min((p.get("low") for p in one_year if p.get("low") is not None),default=None)}
        return {"nifty":nifty,"index_history":index_history,"stats":stats,
                "stock_history":{},"warnings":warnings,"as_of":end.isoformat()}
    return cached("history:v2:"+json.dumps(index_items)+json.dumps(settings.get("watchlist",[])),900,load)


def macro_data():
    settings=config()
    def load():
        rows=[]
        for item in settings["macro"]:
            try:
                # Yahoo chart feed (same source used by yfinance). Potentially delayed.
                response=requests.get("https://query1.finance.yahoo.com/v8/finance/chart/"+quote(item["symbol"],safe=""),
                    params={"range":"3mo","interval":"1d"},headers={"User-Agent":"Mozilla/5.0"},timeout=15)
                response.raise_for_status()
                chart=response.json()["chart"]["result"][0]
                meta=chart["meta"]
                series=[{"date":datetime.fromtimestamp(t,timezone.utc).date().isoformat(),"close":float(c)}
                    for t,c in zip(chart.get("timestamp",[]),chart["indicators"]["quote"][0]["close"])
                    if c is not None and math.isfinite(c)]
                price=meta.get("regularMarketPrice")
                stamp=meta.get("regularMarketTime")
                price_date=datetime.fromtimestamp(stamp,timezone.utc).date().isoformat() if stamp else None
                prior=[p["close"] for p in series if price_date and p["date"]<price_date]
                rows.append({**item,"price":price,"change":change(price,prior[-1] if prior else None),"series":series,
                    "timestamp":datetime.fromtimestamp(stamp,timezone.utc).isoformat() if stamp else None,"error":None})
            except Exception:
                rows.append({**item,"price":None,"change":None,"series":[],"timestamp":None,"error":"Feed unavailable"})
        return {"items":rows,"source":"Yahoo Finance · potentially delayed","fetched_at":datetime.now(IST).isoformat()}
    return cached("macro:"+json.dumps(settings["macro"]),300,load)
