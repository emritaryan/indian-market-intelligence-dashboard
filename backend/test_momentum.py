import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
from pydantic import ValidationError

from main import MomentumInput
from momentum import evaluate_momentum, scan_momentum


class MomentumScannerTests(unittest.TestCase):
    @staticmethod
    def candles(prices, end=date(2026, 9, 20)):
        dates = pd.bdate_range(end=end, periods=len(prices))
        return [{"date": session, "close": price} for session, price in zip(dates, prices)]

    def test_bullish_rules_are_calculated_from_latest_completed_session(self):
        prices = [100 + index * 0.03 for index in range(220)] + [107 + index * 0.8 for index in range(40)]
        row = evaluate_momentum(self.candles(prices), "TEST", "Test Ltd", date(2026, 9, 20))
        self.assertTrue(row["qualifies"])
        self.assertGreater(row["rsi14"], 60)
        self.assertGreater(row["macd_line"], row["signal_line"])
        self.assertGreater(row["close"], row["ema50"])
        self.assertGreater(row["close"], row["ema200"])
        self.assertEqual(row["status"], "Match")

    def test_non_bullish_and_short_history_do_not_qualify(self):
        falling = [150 - index * 0.2 for index in range(260)]
        row = evaluate_momentum(self.candles(falling), "DOWN", "Down Ltd", date(2026, 9, 20))
        self.assertFalse(row["qualifies"])
        self.assertEqual(row["status"], "Filtered out")
        short = evaluate_momentum(self.candles([100] * 100), "SHORT", "Short Ltd", date(2026, 9, 20))
        self.assertEqual(short["status"], "Insufficient history")

    def test_maximum_recommendations_is_fifty(self):
        self.assertEqual(MomentumInput().max_recommendations, 50)
        with self.assertRaises(ValidationError):
            MomentumInput(max_recommendations=51)

    @patch("momentum.fetch_candles")
    @patch("momentum.constituents")
    def test_scan_filters_ranks_and_caps_matches(self, constituents, fetch_candles):
        constituents.return_value = [
            {"Symbol": "FAST", "Company Name": "Fast Ltd"},
            {"Symbol": "SLOW", "Company Name": "Slow Ltd"},
            {"Symbol": "FLAT", "Company Name": "Flat Ltd"},
        ]
        fast = [100 + index * 0.02 for index in range(220)] + [105 + index for index in range(40)]
        slow = [100 + index * 0.02 for index in range(220)] + [105 + index * 0.5 for index in range(40)]
        flat = [100] * 260
        history = {1: self.candles(fast), 2: self.candles(slow), 3: self.candles(flat)}

        def candles_for_token(kite, token, start, end):
            return [item for item in history[token] if start <= item["date"].date() <= end]

        fetch_candles.side_effect = candles_for_token
        kite = MagicMock()
        kite.instruments.return_value = [
            {"tradingsymbol": symbol, "instrument_token": token, "exchange": "NSE", "segment": "NSE", "instrument_type": "EQ"}
            for symbol, token in (("FAST", 1), ("SLOW", 2), ("FLAT", 3))
        ]
        result = scan_momentum(kite, {"max_recommendations": 1}, lambda **values: None)
        self.assertEqual(result["universe_size"], 3)
        self.assertEqual(result["matched_total"], 2)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["rows"][0]["ticker"], "FAST")
        self.assertEqual(result["rows"][0]["rank"], 1)


if __name__ == "__main__":
    unittest.main()

