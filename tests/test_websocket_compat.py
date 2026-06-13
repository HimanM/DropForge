import unittest

from network.websocket import CONNECTION_RESET_ERRORS


class WebsocketCompatibilityTests(unittest.TestCase):
    def test_connection_reset_errors_include_builtin_fallback(self):
        self.assertIn(ConnectionResetError, CONNECTION_RESET_ERRORS)


if __name__ == "__main__":
    unittest.main()
