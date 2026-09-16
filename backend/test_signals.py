import unittest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
import pandas as pd
from signals import crossover, scan
from main import ScanInput
from pydantic import ValidationError

class ScannerTests(unittest.TestCase):
    def candles(self, prices):
        return [{'date': d, 'close': price} for d, price in zip(pd.date_range('2026-01-01', periods=len(prices)), prices)]
    def test_direction_and_values(self):
        for value, expected in [(110, 'Bullish'), (90, 'Bearish'), (100, 'No crossover')]:
            row = crossover(self.candles([100]*35+[value]), 'TEST', 'Test', 6, 30, date(2026,1,1), date(2026,2,28))
            self.assertEqual(row['crossover_type'], expected)
            if value != 100:
                self.assertEqual(row['close'], value)
                self.assertEqual(row['short_sma'], round((500+value)/6,2))
    def test_window_and_partial_day_exclusion(self):
        candles = self.candles([100]*35+[110])
        self.assertEqual(crossover(candles, 'T', 'Test', 6, 30, date(2026,2,6), date(2026,3,1))['crossover_type'], 'No crossover')
        self.assertEqual(crossover(candles, 'T', 'Test', 6, 30, date(2026,1,1), date(2026,2,4))['crossover_type'], 'No crossover')
        self.assertEqual(crossover(candles[:10], 'T', 'Test', 6, 30, date(2026,1,1), date(2026,3,1))['crossover_type'], 'Insufficient history')
    def test_latest_crossover_and_warmup(self):
        values = [100]*35 + [110]*10 + [70]*8
        row = crossover(self.candles(values), 'TEST', 'Test', 6, 30, date(2026,2,5), date(2026,3,1))
        self.assertEqual(row['crossover_type'], 'Bearish')
        self.assertGreater(row['crossover_date'], '2026-02-05')
        # The warm-up observations precede the selected window but initialize SMA 30.
        warm = crossover(self.candles([100]*35+[110]), 'TEST', 'Test', 6, 30, date(2026,2,5), date(2026,2,5))
        self.assertEqual(warm['crossover_type'], 'Bullish')

    def test_settings(self):
        for settings in [{'short_sma': 30}, {'max_stocks':101}, {'lookback_days':0}, {'short_sma':1.5}]:
            with self.assertRaises(ValidationError): ScanInput(**settings)
    @patch('signals.time.sleep')
    @patch('signals.constituents')
    def test_missing_mapping_and_fetch_failure_are_explicit(self, members, sleep):
        members.return_value = [{'Symbol':'A', 'Company Name':'A Ltd'}, {'Symbol':'B','Company Name':'B Ltd'}]
        kite = MagicMock()
        kite.instruments.return_value = [{'tradingsymbol':'A','instrument_token':1,'exchange':'NSE','segment':'NSE','instrument_type':'EQ'}]
        kite.historical_data.side_effect = RuntimeError('network')
        result = scan(kite, ScanInput(max_stocks=2).model_dump(), lambda **kwargs: None)
        self.assertEqual([row['crossover_type'] for row in result['rows']], ['Fetch failed', 'Unmapped'])
        self.assertEqual(len(result['warnings']), 2)
        self.assertEqual([row['rank'] for row in result['rows']], [1,2])

if __name__ == '__main__': unittest.main()
