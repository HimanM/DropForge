import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from web.auth import AuthStore
from web.main import _password
from web.controller import MinerController
from web.server import create_app


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


class PasswordPromptTests(unittest.TestCase):
    def test_short_password_exits_without_reaching_confirmation(self) -> None:
        with patch("web.main.getpass.getpass", return_value="short"):
            with self.assertRaisesRegex(SystemExit, "Invalid password: Password must be at least 12"):
                _password()


class WebStateTests(unittest.TestCase):
    def test_stopped_miner_does_not_expose_stale_device_code(self):
        controller = MinerController()
        controller.manager = SimpleNamespace(
            snapshot=lambda: {
                "login": {
                    "status": "Login required",
                    "user_id": "-",
                    "activation_url": "https://www.twitch.tv/activate",
                    "user_code": "ABCDEFGH",
                }
            }
        )

        snapshot = controller.snapshot()

        self.assertEqual(snapshot["login"]["activation_url"], "")
        self.assertEqual(snapshot["login"]["user_code"], "")


class WebResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_responses_are_never_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            app = create_app(
                Path(directory, "auth.sqlite3"),
                Path(directory),
                auto_start=False,
            )
            async with TestClient(TestServer(app)) as client:
                response = await client.get("/api/session")
                self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_twitch_login_can_be_reset_while_miner_is_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            auth_path = Path(directory, "auth.sqlite3")
            cookies_path = Path(directory, "cookies.jar")
            cookies_path.write_text("saved Twitch session", encoding="utf8")
            AuthStore(auth_path).provision(
                "correct horse battery", "recovery-code-long-enough"
            )
            app = create_app(auth_path, Path(directory), auto_start=False)
            controller = app["controller"]
            controller.start = AsyncMock(return_value=True)
            with patch("web.controller.COOKIES_PATH", cookies_path):
                async with TestClient(TestServer(app)) as client:
                    login = await client.post(
                        "/api/login", json={"password": "correct horse battery"}
                    )
                    csrf = (await login.json())["csrf_token"]
                    response = await client.post(
                        "/api/miner/invalidate-auth",
                        headers={"X-CSRF-Token": csrf},
                    )

            self.assertEqual(response.status, 200)
            self.assertFalse(cookies_path.exists())
            controller.start.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
