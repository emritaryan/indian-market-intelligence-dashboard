import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from overview import IST, market_status, change, quote_data, history_data, macro_data, CACHE

class OverviewTests(unittest.TestCase):
    def setUp(self): CACHE.clear()
    def test_market_boundaries_holidays_and_unknown_calendar(self):
        for hour,minute,opened in [(9,14,False),(9,15,True),(15,29,True),(15,30,False)]:
            self.assertEqual(market_status(datetime(2026,9,15,hour,minute,tzinfo=IST))['is_open'],opened)
        self.assertTrue(market_status(datetime(2026,9,14,10,tzinfo=IST))['label'].startswith('Holiday:'))
        self.assertFalse(market_status(datetime(2026,9,13,10,tzinfo=IST))['is_open'])
        self.assertIn('schedule not configured',market_status(datetime(2026,11,8,18,tzinfo=IST))['label'])
        self.assertIn('needs update',market_status(datetime(2027,1,4,10,tzinfo=IST))['label'])
    @patch('overview.completed_equity_snapshot',return_value={})
    def test_percentage_and_missing_quotes(self,snapshot):
        self.assertEqual(change(110,100),10)
        self.assertIsNone(change(100,0))
        self.assertIsNone(change(None,100))
        kite=MagicMock();kite.quote.return_value={}
        data=quote_data(kite)
        self.assertTrue(all(q['price'] is None for q in data['quotes'].values()))
        quote_data(kite)
        kite.quote.assert_called_once()
    @patch('overview.market_status',return_value={'label':'Market Closed','is_open':False,'ist_time':'2026-09-14T12:00:00+05:30','hours':'09:15–15:30 IST'})
    @patch('overview.completed_equity_snapshot')
    @patch('overview.members',return_value=[{'symbol':'ABB','company':'ABB India','sector':'Capital Goods'}])
    @patch('overview.config',return_value={'indices':[{'symbol':'NIFTY 50','name':'Nifty 50'}]})
    def test_closed_market_uses_completed_nse_session(self,settings,universe,snapshot,status):
        snapshot.return_value={'ABB':{'price':105,'change':5,'timestamp':'2026-09-11T15:30:00+05:30',
            'stale':True,'volume':500,'ohlc':{'open':101,'high':106,'low':100,'close':100},
            'absolute_change':5,'traded_value':52500}}
        kite=MagicMock();kite.quote.return_value={'NSE:ABB':{'last_price':105,'timestamp':datetime(1970,1,1,5,30),
            'ohlc':{'close':105},'volume':0}}
        data=quote_data(kite)
        self.assertEqual(data['quotes']['ABB']['change'],5)
        self.assertEqual(data['quotes']['ABB']['volume'],500)
        self.assertTrue(data['quotes']['ABB']['timestamp'].startswith('2026-09-11'))
    @patch('overview.fetch_candles')
    @patch('overview.config')
    def test_completed_history_and_missing_mapping(self,config,fetch):
        config.return_value={'watchlist':[{'symbol':'MISSING'}]}
        kite=MagicMock();kite.instruments.return_value=[{'tradingsymbol':'NIFTY 50','instrument_token':1,'segment':'INDICES'}]
        fetch.return_value=[{'date':datetime(2026,1,1,tzinfo=IST),'close':100.0}, {'date':datetime(2099,1,1,tzinfo=IST),'close':200.0}]
        data=history_data(kite)
        self.assertEqual(data['nifty'],[{'date':'2026-01-01','close':100.0}])
        self.assertEqual(len(data['warnings']),1)
    @patch('overview.requests.get',side_effect=RuntimeError('offline'))
    def test_macro_failure_is_not_fabricated(self,get):
        data=macro_data()
        self.assertEqual(len(data['items']),4)
        self.assertTrue(all(row['price'] is None and row['error'] for row in data['items']))

if __name__=='__main__':unittest.main()
