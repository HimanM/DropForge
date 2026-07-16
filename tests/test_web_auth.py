import tempfile
import unittest
from pathlib import Path

from web.auth import AuthStore


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AuthStore(Path(self.temp.name, "auth.sqlite3"))

    def tearDown(self):
        self.temp.cleanup()

    def test_password_session_and_recovery_rotation(self):
        self.assertTrue(self.store.provision("correct horse battery", "recovery-code-long-enough"))
        self.assertFalse(self.store.provision("another strong password", "another-recovery-code"))
        self.assertTrue(self.store.verify_password("correct horse battery"))
        self.assertFalse(self.store.verify_password("wrong password"))

        token, session = self.store.create_session()
        self.assertEqual(self.store.get_session(token), session)

        next_recovery = self.store.reset_password(
            "recovery-code-long-enough", "new correct horse battery"
        )
        self.assertIsNotNone(next_recovery)
        self.assertIsNone(self.store.get_session(token))
        self.assertTrue(self.store.verify_password("new correct horse battery"))
        self.assertIsNone(
            self.store.reset_password("recovery-code-long-enough", "third correct horse battery")
        )


if __name__ == "__main__":
    unittest.main()
