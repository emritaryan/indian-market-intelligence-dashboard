"""Bullish momentum scanner for the official Nifty 100 universe."""
from datetime import datetime, timedelta, timezone

import pandas as pd
from kiteconnect.exceptions import TokenException

from signals import constituents, fetch_candles


RULES = {
    "rsi_period": 14,
    "rsi_min": 60,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "ema_short": 50,
    "ema_long": 200,
}


def _rsi(close, period):
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss
    value = 100 - (100 / (1 + relative_strength))
    value = value.mask((average_loss == 0) & (average_gain > 0), 100)
    return value.mask((average_loss == 0) & (average_gain == 0), 50)


def evaluate_momentum(candles, symbol, company, end):
    """Calculate the fixed bullish rules for the latest completed session."""
    row = {
        "ticker": symbol,
        "company": company,
        "as_of": None,
        "close": None,
        "rsi14": None,
        "macd_line": None,
        "signal_line": None,
        "macd_spread": None,
        "ema50": None,
        "ema200": None,
        "above_ema50_percent": None,
        "above_ema200_percent": None,
        "qualifies": False,
        "status": "No data",
    }
    if not candles:
        return row

    data = pd.DataFrame(candles)
    if not {"date", "close"}.issubset(data.columns):
        return row
    data["session"] = pd.to_datetime(data["date"], errors="coerce").dt.date
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data = data.dropna(subset=["session", "close"]).sort_values("session").drop_duplicates("session")
    data = data[data["session"] <= end].copy()
    if len(data) < RULES["ema_long"]:
        row["status"] = "Insufficient history"
        return row

    close = data["close"]
    data["rsi14"] = _rsi(close, RULES["rsi_period"])
    data["ema50"] = close.ewm(span=RULES["ema_short"], adjust=False,
                               min_periods=RULES["ema_short"]).mean()
    data["ema200"] = close.ewm(span=RULES["ema_long"], adjust=False,
                                min_periods=RULES["ema_long"]).mean()
    fast = close.ewm(span=RULES["macd_fast"], adjust=False,
                     min_periods=RULES["macd_fast"]).mean()
    slow = close.ewm(span=RULES["macd_slow"], adjust=False,
                     min_periods=RULES["macd_slow"]).mean()
    data["macd_line"] = fast - slow
    data["signal_line"] = data["macd_line"].ewm(
        span=RULES["macd_signal"], adjust=False, min_periods=RULES["macd_signal"]
    ).mean()

    latest = data.iloc[-1]
    required = ["close", "rsi14", "ema50", "ema200", "macd_line", "signal_line"]
    if any(pd.isna(latest[key]) for key in required):
        row["status"] = "Insufficient history"
        return row

    close_value = float(latest["close"])
    rsi = float(latest["rsi14"])
    ema50 = float(latest["ema50"])
    ema200 = float(latest["ema200"])
    macd_line = float(latest["macd_line"])
    signal_line = float(latest["signal_line"])
    qualifies = (
        rsi > RULES["rsi_min"]
        and macd_line > signal_line
        and close_value > ema50
        and close_value > ema200
    )
    row.update(
        as_of=latest["session"].isoformat(),
        close=round(close_value, 2),
        rsi14=round(rsi, 2),
        macd_line=round(macd_line, 2),
        signal_line=round(signal_line, 2),
        macd_spread=round(macd_line - signal_line, 2),
        ema50=round(ema50, 2),
        ema200=round(ema200, 2),
        above_ema50_percent=round((close_value / ema50 - 1) * 100, 2),
        above_ema200_percent=round((close_value / ema200 - 1) * 100, 2),
        qualifies=qualifies,
        status="Match" if qualifies else "Filtered out",
    )
    return row


def scan_momentum(kite, settings, update):
    """Scan all Nifty 100 stocks and return no more than the requested 50 matches."""
    members = constituents()
    update(total=len(members), message="Mapping NSE equity instruments…")
    instruments = kite.instruments("NSE")
    tokens = {
        item["tradingsymbol"]: item["instrument_token"]
        for item in instruments
        if item.get("exchange") == "NSE"
        and item.get("segment") == "NSE"
        and item.get("instrument_type") == "EQ"
    }
    india = timezone(timedelta(hours=5, minutes=30))
    end = datetime.now(india).date() - timedelta(days=1)
    # Five hundred calendar days supplies comfortably more than 200 trading sessions.
    fetch_start = end - timedelta(days=500)
    matches, warnings = [], []
    evaluated = 0
    latest_session = None

    for index, member in enumerate(members):
        symbol, company = member["Symbol"], member["Company Name"]
        update(completed=index, message=f"Evaluating {symbol}")
        if symbol not in tokens:
            warnings.append(f"{symbol}: no NSE equity instrument mapping.")
            update(completed=index + 1)
            continue
        try:
            candles, cursor = [], fetch_start
            while cursor <= end:
                chunk_end = min(cursor + timedelta(days=364), end)
                candles.extend(fetch_candles(kite, tokens[symbol], cursor, chunk_end))
                cursor = chunk_end + timedelta(days=1)
            row = evaluate_momentum(candles, symbol, company, end)
            if row["status"] in {"No data", "Insufficient history"}:
                warnings.append(f"{symbol}: {row['status'].lower()}.")
            else:
                evaluated += 1
                if row["as_of"] and (latest_session is None or row["as_of"] > latest_session):
                    latest_session = row["as_of"]
                if row["qualifies"]:
                    matches.append(row)
        except TokenException:
            raise
        except Exception:
            warnings.append(f"{symbol}: history unavailable; check Kite data access or retry.")
        update(completed=index + 1)

    matches.sort(key=lambda row: (-row["rsi14"], -row["macd_spread"], row["ticker"]))
    matched_total = len(matches)
    rows = matches[: settings["max_recommendations"]]
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return {
        "rows": rows,
        "warnings": warnings,
        "universe_size": len(members),
        "evaluated": evaluated,
        "matched_total": matched_total,
        "as_of": latest_session or end.isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settings": {**RULES, **settings},
        "ranking": "RSI descending, then MACD spread descending",
    }

