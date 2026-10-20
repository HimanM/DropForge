import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientConnectionError
from aiohttp.test_utils import TestClient, TestServer

from core.constants import GQL_QUERIES
from core.exceptions import ReloadRequest
from network.twitch import Twitch, _AuthState
from web.auth import AuthStore
from web.catalog import WebTwitch
from web.claims import PendingClaims
from web.controller import MinerController
from web.manager import WebLogin
from web.server import create_app
from tui.state import TUIState
from web.twitch_auth import TV_CLIENT, WebDeviceAuth


TOKEN = "test_device_token_not_a_real_credential"


async def await_coro(coro):
    return await coro


class DeviceAuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name, "web-device-session.json")
        self.client = SimpleNamespace(
            gui=SimpleNamespace(
                login=SimpleNamespace(update=Mock(), ask_enter_code=AsyncMock()),
                status=SimpleNamespace(update=Mock()), coro_unless_closed=await_coro,
            ),
            settings=SimpleNamespace(proxy=""),
            get_session=AsyncMock(return_value=SimpleNamespace(headers={})), print=Mock(),
            stop_watching=Mock(), change_state=Mock(),
        )
        self.auth = WebDeviceAuth(self.client, self.path)
        self.identity = {"client_id": TV_CLIENT.CLIENT_ID, "user_id": "123", "expires_in": 0}

    def tearDown(self):
        self.temp.cleanup()

    def save_session(self):
        self.path.write_text(json.dumps({"access_token": TOKEN, "client_id": TV_CLIENT.CLIENT_ID,
                                         "device_id": "device"}), encoding="utf8")

    async def test_cookie_independent_restore_and_hourly_validation(self):
        self.save_session()
        self.auth._json = AsyncMock(return_value=(200, self.identity))
        self.auth._oauth_login = AsyncMock()
        with patch("network.twitch.acquire_integrity_token", new=AsyncMock()) as browser:
            await self.auth.validate()
            await self.auth.validate()
            self.assertIsNone(await self.auth.get_integrity_token(force_refresh=True))
            browser.assert_not_awaited()
        self.assertEqual(self.auth.user_id, 123)
        self.assertEqual(self.auth.access_token, TOKEN)
        self.auth._json.assert_awaited_once()
        self.auth._oauth_login.assert_not_awaited()
        self.auth._validate_after = 0
        await self.auth.validate()
        self.assertEqual(self.auth._json.await_count, 2)

    async def test_new_session_written_atomically_after_validation(self):
        self.auth._oauth_login = AsyncMock(return_value=TOKEN)
        self.auth._json = AsyncMock(return_value=(200, self.identity))
        await self.auth.validate()
        self.assertEqual(json.loads(self.path.read_text())["access_token"], TOKEN)
        self.assertFalse(self.path.with_suffix(".json.new").exists())
        if __import__("os").name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    async def test_gql_invalidation_does_not_delete_saved_credentials(self):
        self.save_session()
        original = self.path.read_bytes()
        self.auth.invalidate(delete_cookies=True)
        self.assertEqual(self.path.read_bytes(), original)
        self.auth._json = AsyncMock(return_value=(200, self.identity))
        await self.auth.validate()
        self.assertEqual(self.auth.access_token, TOKEN)

    async def test_only_oauth_401_requests_new_activation(self):
        self.save_session()
        self.client.gui.notifier = Mock()
        new_token = TOKEN + "_replacement"
        self.auth._json = AsyncMock(side_effect=[(401, {}), (200, self.identity)])
        self.auth._oauth_login = AsyncMock(return_value=new_token)
        await self.auth.validate()
        self.auth._oauth_login.assert_awaited_once()
        self.client.stop_watching.assert_called_once()
        self.client.change_state.assert_called_once()
        self.client.gui.notifier.auth_issue.assert_called_once()
        self.assertEqual(self.client.gui.notifier.auth_issue.call_args.args[0], "expired")
        self.assertEqual(json.loads(self.path.read_text())["access_token"], new_token)

    async def test_login_success_clears_warning_but_not_query_permission_warning(self):
        notifier = Mock()
        notifier.auth_alert.return_value = {"kind": "expired"}
        manager = SimpleNamespace(notifier=notifier, state=TUIState(), refresh_login=Mock())
        login = WebLogin(manager)
        login.update("Logged in", 123)
        notifier.auth_recovered.assert_called_once()
        notifier.auth_recovered.reset_mock()
        for kind in ("permissions", "verification", "login_error"):
            notifier.auth_alert.return_value = {"kind": kind}
            login.update("Logged in", 123)
            notifier.auth_recovered.assert_not_called()

    async def test_outage_keeps_session_and_recovers(self):
        self.save_session()
        original = self.path.read_bytes()
        class Response:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def json(inner): return self.identity
        session = SimpleNamespace(headers={}, request=Mock(side_effect=[ClientConnectionError(), Response()]))
        self.client.get_session = AsyncMock(return_value=session)
        with patch("web.twitch_auth.asyncio.sleep", new=AsyncMock()):
            await self.auth.validate()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(session.request.call_count, 2)

    async def test_device_polling_slow_down_and_expired_code(self):
        device = {"device_code": "private_poll_code", "user_code": "PUBLICCODE", "expires_in": 600}
        self.auth._json = AsyncMock(side_effect=[
            (200, device), (400, {"message": "slow_down"}),
            (400, {"message": "expired_token"}), (200, device),
            (400, {"message": "authorization_pending"}), (200, {"access_token": TOKEN}),
        ])
        with patch("web.twitch_auth.asyncio.sleep", new=AsyncMock()) as sleep:
            self.assertEqual(await self.auth._oauth_login(), TOKEN)
        self.assertEqual(self.client.gui.login.ask_enter_code.await_count, 2)
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [5, 10, 5, 5])
        self.assertNotIn("private_poll_code", str(self.client.print.call_args_list))

    async def test_web_opt_in_does_not_change_desktop_auth(self):
        desktop = Twitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace())
        web = WebTwitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace(), browser_free=True)
        legacy = WebTwitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace())
        self.assertIs(type(desktop._auth_state), _AuthState)
        self.assertIs(type(legacy._auth_state), _AuthState)
        self.assertIsInstance(web._auth_state, WebDeviceAuth)

    async def test_device_http_never_loads_or_overwrites_browser_cookies(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "cookies.jar")
            path.write_bytes(b"existing browser cookies")
            client = WebTwitch(SimpleNamespace(connection_quality=1), gui_factory=lambda _: SimpleNamespace(), browser_free=True)
            with patch("network.twitch.aiohttp.CookieJar.load", side_effect=AssertionError("Browser cookies must not be loaded")):
                session = await client.get_session()
                try:
                    self.assertEqual(len(session.cookie_jar), 0)
                    session.cookie_jar.save(path)
                finally:
                    await session.close()
            self.assertEqual(path.read_bytes(), b"existing browser cookies")

    async def test_device_gql_permission_error_revalidates_without_browser(self):
        web = WebTwitch(SimpleNamespace(), gui_factory=lambda _: self.client.gui, browser_free=True)
        web.get_auth = AsyncMock()
        web.print = Mock()
        with patch("network.twitch.Twitch.gql_request", new=AsyncMock(side_effect=[ReloadRequest(), {"data": {}}])) as gql:
            with patch("web.catalog.asyncio.sleep", new=AsyncMock()):
                self.assertEqual(await web.gql_request(GQL_QUERIES["Inventory"]), {"data": {}})
        self.assertEqual(gql.await_count, 2)
        web.get_auth.assert_awaited_once()


class PendingClaimTests(unittest.IsolatedAsyncioTestCase):
    async def test_receipt_survives_restart_and_inventory_confirms(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AuthStore(Path(directory, "auth.sqlite3"))
            client = WebTwitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace(), store=store)
            key = "123#campaign#drop"
            claim = GQL_QUERIES["ClaimDrop"].with_variables({"input": {"dropInstanceID": key}})
            accepted = {"data": {"claimDropRewards": {"status": "ELIGIBLE_FOR_ALL"}}}
            client._gql_request = AsyncMock(return_value=accepted)
            await client.gql_request(claim)
            restarted = WebTwitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace(), store=store)
            restarted._gql_request = AsyncMock()
            self.assertEqual(await restarted.gql_request(claim), accepted)
            restarted._gql_request.assert_not_awaited()
            receipt = restarted.pending_claims
            self.assertTrue(receipt.recent(key))
            receipt.reconcile({"data": {"currentUser": {"inventory": {"dropCampaignsInProgress": [
                {"timeBasedDrops": [{"self": {"dropInstanceID": key, "isClaimed": False}}]},
            ]}}}})
            self.assertTrue(receipt.recent(key))
            receipt.reconcile({"data": {"currentUser": {"inventory": {"dropCampaignsInProgress": [
                {"timeBasedDrops": [{"self": {"dropInstanceID": key, "isClaimed": True}}]},
            ]}}}})
            self.assertFalse(PendingClaims(store).recent(key))

    async def test_hourly_retry_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            claims = PendingClaims(AuthStore(Path(directory, "auth.sqlite3")))
            with patch("web.claims.time", return_value=10000):
                claims.accepted("123#campaign#drop")
                self.assertTrue(claims.recent("123#campaign#drop"))
                self.assertFalse(claims.recent("456#campaign#drop"))
            with patch("web.claims.time", return_value=13601):
                self.assertFalse(claims.recent("123#campaign#drop"))


class DeviceLoginApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_device_login_requires_authentication_and_csrf(self):
        with tempfile.TemporaryDirectory() as directory:
            auth_path = Path(directory, "auth.sqlite3")
            AuthStore(auth_path).provision("correct horse battery", "recovery-code-long-enough")
            app = create_app(auth_path, Path(directory), auto_start=False)
            controller = app["controller"]
            controller.use_device_login = AsyncMock()
            async with TestClient(TestServer(app)) as client:
                self.assertEqual((await client.post("/api/twitch/device-login")).status, 401)
                login = await client.post("/api/login", json={"password": "correct horse battery"})
                csrf = (await login.json())["csrf_token"]
                self.assertEqual((await client.post("/api/twitch/device-login")).status, 403)
                response = await client.post("/api/twitch/device-login", headers={"X-CSRF-Token": csrf})
                self.assertEqual(response.status, 200)
            controller.use_device_login.assert_awaited_once()

    async def test_device_reset_removes_only_device_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AuthStore(Path(directory, "auth.sqlite3"))
            store.update_settings({"twitch_login_method": "device"})
            controller = MinerController(store=store)
            controller.stop = AsyncMock()
            controller.start = AsyncMock(return_value=True)
            path = Path(directory, "web-device-session.json")
            path.write_text("test device session")
            legacy = Path(directory, "cookies.jar")
            legacy.write_text("existing browser session")
            with patch("web.controller.DEVICE_SESSION_PATH", path):
                await controller.reset_auth()
            self.assertFalse(path.exists())
            self.assertEqual(legacy.read_text(), "existing browser session")
            controller.start.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
