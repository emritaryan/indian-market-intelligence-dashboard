import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from kiteconnect.exceptions import TokenException
import main

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.saved = patch.object(main, 'SESSION_FILE', Path(self.directory.name) / 'session.bin')
        self.saved.start()
        self.client = TestClient(main.app)
        self.kite = MagicMock()
        self.kite.generate_session.return_value = {'access_token': 'private-test-token'}
        self.kite.profile.return_value = {'user_name': 'Test User', 'user_id': 'TEST01', 'products': ['CNC'], 'exchanges': ['NSE'], 'access_token': 'must-not-leak'}
        self.mock = patch.object(main, 'KiteConnect', return_value=self.kite)
        self.mock.start()
    def tearDown(self):
        self.mock.stop()
        self.saved.stop()
        self.directory.cleanup()
    def login(self):
        return self.client.post('/api/login', json={'api_key': 'test-key', 'api_secret': 'test-secret', 'request_token': 'test-request'})
    def test_saved_session_and_allowlist(self):
        self.assertEqual(self.client.get('/api/profile').status_code, 401)
        result = self.login()
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('access_token', result.text)
        self.assertNotIn(b'private-test-token', main.SESSION_FILE.read_bytes())
        # A new client request loads the encrypted file, without another exchange.
        self.assertEqual(self.client.get('/api/profile').json()['user_id'], 'TEST01')
        self.kite.generate_session.assert_called_once()
        self.kite.set_access_token.assert_called_with('private-test-token')
        self.client.post('/api/logout')
        self.assertFalse(main.SESSION_FILE.exists())
    def test_expiry_and_network_error(self):
        self.login()
        self.kite.profile.side_effect = RuntimeError('secret response')
        self.assertEqual(self.client.get('/api/profile').status_code, 502)
        self.assertTrue(main.SESSION_FILE.exists())
        self.kite.profile.side_effect = TokenException('expired')
        self.assertEqual(self.client.get('/api/profile').status_code, 401)
        self.assertFalse(main.SESSION_FILE.exists())
    def test_cross_site_and_rejected_login(self):
        self.assertEqual(self.client.post('/api/logout', headers={'Origin': 'https://example.com'}).status_code, 403)
        self.kite.generate_session.side_effect = TokenException('secret response')
        result = self.login()
        self.assertEqual(result.status_code, 401)
        self.assertNotIn('secret response', result.text)
        self.assertFalse(main.SESSION_FILE.exists())

if __name__ == '__main__':
    unittest.main()
