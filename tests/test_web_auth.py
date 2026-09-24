import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from core.constants import ClientType
from web.auth import AuthStore
from web.main import _TerminalLogin, _login_twitch_android, _password
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


class TwitchTerminalLoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_credentials_are_reused_only_for_the_2fa_prompt(self) -> None:
        form = _TerminalLogin()
        with (
            patch("builtins.input", return_value="streamer"),
            patch("web.main.getpass.getpass", side_effect=["secret-password", "123456"]),
        ):
            first = await form.ask_login()
            second = await form.ask_login()

        self.assertEqual(
            (first.username, first.password, first.token),
            ("streamer", "secret-password", ""),
        )
        self.assertEqual(second.token, "123456")

    async def test_android_login_closes_session_before_saving_token(self) -> None:
        session = SimpleNamespace(close=AsyncMock())
        auth = SimpleNamespace(_login=AsyncMock(return_value="android-token"))
        client = SimpleNamespace(_auth_state=auth, _session=session)
        result = {"client": "Twitch Android", "user_id": 123, "campaign_count": 42}

        with (
            patch("web.main.Settings"),
            patch("web.main.Twitch", return_value=client),
            patch("web.main.import_auth_token", new=AsyncMock(return_value=result)) as save,
        ):
            self.assertEqual(await _login_twitch_android(), result)

        self.assertEqual(client._client_type.CLIENT_ID, ClientType.ANDROID_APP.CLIENT_ID)
        self.assertEqual(len(auth.device_id), 32)
        session.close.assert_awaited_once()
        save.assert_awaited_once_with("android-token")


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


class MinerSupervisorTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_engine_restarts_until_stopped(self) -> None:
        controller = MinerController()
        controller._run_once = AsyncMock(side_effect=[True, False])

        async def timeout(awaitable, **_kwargs):
            awaitable.close()
            raise asyncio.TimeoutError

        with patch(
            "web.controller.asyncio.wait_for",
            new=timeout,
        ):
            await controller._run()

        self.assertEqual(controller._run_once.await_count, 2)

    async def test_manual_stop_prevents_restart(self) -> None:
        controller = MinerController()

        async def stopped_attempt():
            controller._stop_requested.set()
            return True

        controller._run_once = AsyncMock(side_effect=stopped_attempt)
        await controller._run()

        controller._run_once.assert_awaited_once()


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

    async def test_twitch_token_import_never_echoes_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            auth_path = Path(directory, "auth.sqlite3")
            AuthStore(auth_path).provision(
                "correct horse battery", "recovery-code-long-enough"
            )
            app = create_app(auth_path, Path(directory), auto_start=False)
            app["controller"].import_twitch_token = AsyncMock(
                return_value={"client": "Twitch web", "user_id": 123, "campaign_count": 42}
            )
            async with TestClient(TestServer(app)) as client:
                login = await client.post(
                    "/api/login", json={"password": "correct horse battery"}
                )
                csrf = (await login.json())["csrf_token"]
                secret = "temporary_auth_token_value_12345"
                response = await client.post(
                    "/api/twitch/import-token",
                    headers={"X-CSRF-Token": csrf},
                    json={"token": secret},
                )
                body = await response.json()

            self.assertEqual(response.status, 200)
            self.assertNotIn(secret, str(body))
            app["controller"].import_twitch_token.assert_awaited_once_with(secret)


if __name__ == "__main__":
    unittest.main()
