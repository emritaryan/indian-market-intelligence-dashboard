import unittest

from stock import build_fundamental_metrics


class FundamentalMetricTests(unittest.TestCase):
    def test_kite_price_recalculates_price_dependent_metrics(self):
        info = {"sharesOutstanding": 10, "trailingEps": 5, "bookValue": 20,
                "trailingAnnualDividendRate": 2, "debtToEquity": 44,
                "returnOnEquity": 0.0894}
        metrics = build_fundamental_metrics(info, 100)
        self.assertEqual(metrics["market_cap"], 1000)
        self.assertEqual(metrics["stock_pe"], 20)
        self.assertEqual(metrics["pb_ratio"], 5)
        self.assertEqual(metrics["debt_to_equity"], 0.44)
        self.assertAlmostEqual(metrics["roe"], 8.94)
        self.assertEqual(metrics["dividend_yield"], 2)
        self.assertIsNone(metrics["industry_pe"])
        self.assertIsNone(metrics["face_value"])

    def test_roe_falls_back_to_net_income_over_book_equity(self):
        info = {"sharesOutstanding": 10, "bookValue": 20, "netIncomeToCommon": 18}
        metrics = build_fundamental_metrics(info, 100)
        self.assertAlmostEqual(metrics["roe"], 9)


if __name__ == "__main__":
    unittest.main()
