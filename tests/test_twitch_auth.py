import asyncio
import unittest
from types import SimpleNamespace

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from yarl import URL

from core.constants import ClientType
from core.exceptions import GQLException, LoginException
from network.integrity import acquire_integrity_token
from network.twitch import Twitch, _AuthState, import_auth_token, validate_auth_token


class _Response:
    status = 400

    async def json(self):
        return {"status": 400, "message": "invalid client"}


class _Request:
    async def __aenter__(self):
        return _Response()

    async def __aexit__(self, *args):
        return False


class TwitchAuthTests(unittest.TestCase):
    def test_working_device_login_client_is_default(self):
        twitch = Twitch(
            SimpleNamespace(),
            gui_factory=lambda _: SimpleNamespace(),
        )
        self.assertIs(twitch._client_type, ClientType.MOBILE_WEB)

    def test_device_login_error_is_reported_without_key_error(self):
        twitch = SimpleNamespace(
            _client_type=ClientType.MOBILE_WEB,
            gui=SimpleNamespace(login=SimpleNamespace()),
            request=lambda *args, **kwargs: _Request(),
        )
        auth = _AuthState(twitch)
        auth.device_id = "test-device"

        with self.assertRaisesRegex(LoginException, "invalid client"):
            asyncio.run(auth._oauth_login())


class TwitchIntegrityTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_receives_matching_identity_before_loading_twitch(self):
        class Context:
            def __init__(self, value):
                self.value = value

            async def __aenter__(self):
                return self.value

            async def __aexit__(self, *_args):
                return False

        class Response:
            async def json(self):
                return {"webSocketDebuggerUrl": "ws://browser"}

        class Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            def put(self, *_args, **_kwargs):
                return Context(Response())

            def ws_connect(self, *_args, **_kwargs):
                return Context(object())

        process = SimpleNamespace(
            pid=123,
            poll=Mock(return_value=None),
            terminate=Mock(),
            wait=Mock(return_value=0),
        )
        browser_call = AsyncMock(
            side_effect=[
                {},
                {},
                {"result": {"value": "Mozilla/5.0 (X11; Linux x86_64) Chrome/151"}},
                {"success": True},
                {},
                {},
                {
                    "result": {
                        "value": {
                            "token": "proof",
                            "expiration": 1890000000000,
                            "probe": {"status": 200, "errors": []},
                        }
                    }
                },
            ]
        )
        with (
            patch("network.integrity._browser", return_value="browser"),
            patch("network.integrity.subprocess.Popen", return_value=process),
            patch("network.integrity.aiohttp.ClientSession", return_value=Session()),
            patch("network.integrity._call", browser_call),
            patch("network.integrity.asyncio.sleep", new=AsyncMock()),
            patch("network.integrity.os.killpg", create=True),
        ):
            proof, expiration, user_agent = await acquire_integrity_token(
                {"Authorization": "OAuth secret", "Client-ID": "client"},
                "device",
                {"operationName": "ViewerDropsDashboard"},
            )

        self.assertEqual((proof, expiration), ("proof", 1890000000))
        self.assertEqual(user_agent, "Mozilla/5.0 (X11; Linux x86_64) Chrome/151")
        user_agent_call = browser_call.await_args_list[2]
        self.assertEqual(user_agent_call.args[2], "Runtime.evaluate")
        self.assertEqual(user_agent_call.args[3]["expression"], "navigator.userAgent")
        cookie = browser_call.await_args_list[3].args[3]
        self.assertEqual(cookie["name"], "auth-token")
        self.assertEqual(cookie["value"], "secret")
        self.assertEqual(browser_call.await_args_list[5].args[2], "Page.navigate")
        expression = browser_call.await_args_list[6].args[3]["expression"]
        self.assertIn("ViewerDropsDashboard", expression)
        self.assertIn("Client-Integrity", expression)


class TwitchTokenImportAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.integrity = patch(
            "network.twitch.acquire_integrity_token",
            new=AsyncMock(
                return_value=("test_integrity_token_abc", 1890000000, "test-browser-agent")
            ),
        )
        self.integrity_mock = self.integrity.start()
        self.addCleanup(self.integrity.stop)

    async def test_validate_auth_token_succeeds_with_null_campaigns(self):
        class MockSession:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            def get(self, url, headers):
                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {"client_id": ClientType.WEB.CLIENT_ID, "user_id": 123456}

                return Resp()

            def post(self, url, headers, json):
                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {"data": {"currentUser": {"dropCampaigns": None}}}

                return Resp()

        with patch("aiohttp.ClientSession", MockSession):
            client, user_id, count = await validate_auth_token("valid_token_value_here_12345")
            self.assertIs(client, ClientType.WEB)
            self.assertEqual(user_id, 123456)
            self.assertEqual(count, 0)

    async def test_validate_auth_token_succeeds_with_partial_gql_errors(self):
        class MockSession:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            def get(self, url, headers):
                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {"client_id": ClientType.WEB.CLIENT_ID, "user_id": 987654}

                return Resp()

            def post(self, url, headers, json):
                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {
                            "data": {"currentUser": {"dropCampaigns": [{"id": "c1"}, {"id": "c2"}]}},
                            "errors": [{"message": "service error", "path": ["currentUser", "dropCampaigns", 0]}],
                        }

                return Resp()

        with patch("aiohttp.ClientSession", MockSession):
            client, user_id, count = await validate_auth_token("valid_token_value_here_12345")
            self.assertIs(client, ClientType.WEB)
            self.assertEqual(user_id, 987654)
            self.assertEqual(count, 2)

    async def test_validate_auth_token_retries_persisted_query(self):
        post_calls = []

        class MockSession:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            def get(self, url, headers):
                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {"client_id": ClientType.WEB.CLIENT_ID, "user_id": 55555}

                return Resp()

            def post(self, url, headers, json):
                if op := json.get("operationName"):
                    post_calls.append(op)

                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        if not post_calls:
                            return {}
                        if len(post_calls) == 1:
                            return {"errors": [{"message": "PersistedQueryNotFound"}]}
                        return {
                            "data": {"currentUser": {"dropCampaigns": [{"id": "c1"}]}}
                        }

                return Resp()

        with patch("aiohttp.ClientSession", MockSession):
            client, user_id, count = await validate_auth_token("valid_token_value_here_12345")
            self.assertIs(client, ClientType.WEB)
            self.assertEqual(user_id, 55555)
            self.assertEqual(count, 1)
            self.assertEqual(post_calls, ["ViewerDropsDashboard", "ViewerDropsDashboard"])

    async def test_validate_auth_token_rejects_invalid_token(self):
        class MockSession:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            def get(self, url, headers):
                class Resp:
                    status = 401

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {"status": 401, "message": "invalid access token"}

                return Resp()

        with patch("aiohttp.ClientSession", MockSession):
            with self.assertRaisesRegex(ValueError, "Twitch rejected this auth token"):
                await validate_auth_token("invalid_token_long_enough_12345")

    async def test_oauth_login_reports_error_and_allows_subsequent_login(self):
        login_form = SimpleNamespace(
            ask_auth_token=AsyncMock(side_effect=["short", ""]),
            report_import_error=Mock(),
        )
        twitch = SimpleNamespace(
            _client_type=ClientType.MOBILE_WEB,
            gui=SimpleNamespace(login=login_form),
            print=Mock(),
            request=lambda *args, **kwargs: _Request(),
        )
        auth = _AuthState(twitch)
        auth.device_id = "test-device"

        with self.assertRaisesRegex(LoginException, "invalid client"):
            await auth._oauth_login()

        login_form.report_import_error.assert_called_once()

    async def test_find_cookie_matches_alternative_domains(self):
        jar = aiohttp.CookieJar()
        jar.update_cookies({"auth-token": "secret_token"}, response_url=URL("https://www.twitch.tv"))

        # When querying for m.twitch.tv, _find_cookie should locate the cookie saved under www.twitch.tv
        found = _AuthState._find_cookie(jar, URL("https://m.twitch.tv"))
        self.assertIn("auth-token", found)
        self.assertEqual(found["auth-token"].value, "secret_token")

    async def test_import_auth_token_saves_domain_wide_cookie(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir, "cookies.jar")
            with patch("network.twitch.validate_auth_token", return_value=(ClientType.WEB, 12345, 3)):
                result = await import_auth_token("valid_token_value_here_12345", path=cookie_file)
                self.assertEqual(result["user_id"], 12345)
                self.assertEqual(result["campaign_count"], 3)

            loaded_jar = aiohttp.CookieJar()
            loaded_jar.load(cookie_file)
            self.assertIn("auth-token", loaded_jar.filter_cookies(URL("https://www.twitch.tv")))
            self.assertIn("auth-token", loaded_jar.filter_cookies(URL("https://m.twitch.tv")))
            self.assertIn("auth-token", loaded_jar.filter_cookies(URL("https://gql.twitch.tv")))

    async def test_failed_import_preserves_saved_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir, "cookies.jar")
            cookie_file.write_bytes(b"existing session")
            with patch(
                "network.twitch.validate_auth_token",
                side_effect=ValueError("invalid token"),
            ):
                with self.assertRaisesRegex(ValueError, "invalid token"):
                    await import_auth_token("invalid_token_value_here_12345", path=cookie_file)
            self.assertEqual(cookie_file.read_bytes(), b"existing session")


    async def test_validate_auth_token_includes_integrity_token(self):
        recorded_headers = []

        class MockSession:
            def __init__(self, *_args, **_kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                pass

            def get(self, url, headers):
                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {"client_id": ClientType.WEB.CLIENT_ID, "user_id": 99999}

                return Resp()

            def post(self, url, headers, json):
                recorded_headers.append((url, dict(headers)))

                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        return {"data": {"currentUser": {"dropCampaigns": [{"id": "c1"}]}}}

                return Resp()

        with patch("aiohttp.ClientSession", MockSession):
            client, user_id, count = await validate_auth_token("valid_token_value_here_12345")
            self.assertEqual(count, 1)
            gql_headers = [h for u, h in recorded_headers if "gql" in u and "integrity" not in u]
            self.assertTrue(any(h.get("Client-Integrity") == "test_integrity_token_abc" for h in gql_headers))
            self.assertTrue(any(h.get("User-Agent") == "test-browser-agent" for h in gql_headers))

    async def test_get_integrity_token_caches_and_refreshes(self):
        twitch = SimpleNamespace(
            _client_type=ClientType.WEB,
        )
        auth = _AuthState(twitch)
        auth.session_id = "test-session"
        auth.device_id = "test-device"
        auth.access_token = "test-access"
        self.integrity_mock.side_effect = [
            ("token_1", 1890000000, "browser-agent-1"),
            ("token_2", 1890000000, "browser-agent-2"),
        ]

        # First fetch acquires token
        token1 = await auth.get_integrity_token()
        self.assertEqual(token1, "token_1")
        self.assertEqual(self.integrity_mock.await_count, 1)

        # Subsequent fetch uses cache
        token2 = await auth.get_integrity_token()
        self.assertEqual(token2, "token_1")
        self.assertEqual(self.integrity_mock.await_count, 1)

        # Force refresh fetches a new token
        token3 = await auth.get_integrity_token(force_refresh=True)
        self.assertEqual(token3, "token_2")
        self.assertEqual(self.integrity_mock.await_count, 2)

    def test_auth_headers_include_client_integrity(self):
        twitch = SimpleNamespace(_client_type=ClientType.WEB)
        auth = _AuthState(twitch)
        auth.access_token = "dummy-token"
        auth.integrity_token = "dummy-integrity"

        headers = auth.headers(gql=True)
        self.assertEqual(headers.get("Client-Integrity"), "dummy-integrity")
        self.assertEqual(headers.get("Authorization"), "OAuth dummy-token")

    async def test_gql_request_retries_on_failed_integrity_check(self):
        attempts = 0

        class MockGQLResponse:
            async def json(self):
                nonlocal attempts
                attempts += 1
                if attempts == 1:
                    return {
                        "errors": [
                            {
                                "message": "failed integrity check",
                                "path": ["currentUser", "dropCampaigns"],
                                "extensions": {"code": "IntegrityCheckFailed"},
                            }
                        ]
                    }
                return {"data": {"currentUser": {"dropCampaigns": [{"id": "c1"}]}}}

        class MockRequestCtx:
            def __init__(self, response):
                self._response = response

            async def __aenter__(self):
                return self._response

            async def __aexit__(self, *args):
                return False

        gui = SimpleNamespace(status=SimpleNamespace(update=Mock()), inv=SimpleNamespace(clear=Mock(), add=Mock()))
        twitch = Twitch(SimpleNamespace(dump=False), gui_factory=lambda _: gui)
        auth = _AuthState(twitch)
        auth.access_token = "test-token"
        auth.user_id = 1234
        auth.session_id = "session-123"
        auth.device_id = "device-123"
        auth.integrity_user_agent = "browser-agent"
        auth._logged_in.set()
        twitch._auth_state = auth

        refresh_called = False
        orig_get_integrity = auth.get_integrity_token

        async def mock_get_integrity(*, force_refresh: bool = False):
            nonlocal refresh_called
            if force_refresh:
                refresh_called = True
            return "mock_integrity"

        auth.get_integrity_token = mock_get_integrity

        request_headers = []

        def mock_request(method, url, **kwargs):
            request_headers.append(kwargs["headers"])
            return MockRequestCtx(MockGQLResponse())

        twitch.request = mock_request

        result = await twitch.gql_request({"operationName": "ViewerDropsDashboard"})
        self.assertEqual(attempts, 2)
        self.assertTrue(refresh_called)
        self.assertTrue(all(headers["User-Agent"] == "browser-agent" for headers in request_headers))
        self.assertEqual(result["data"]["currentUser"]["dropCampaigns"], [{"id": "c1"}])

    async def test_gql_request_raises_on_unresolvable_integrity_failure(self):
        class MockGQLResponse:
            async def json(self):
                return {
                    "data": {"currentUser": {"dropCampaigns": [{"id": "bad"}]}},
                    "errors": [
                        {
                            "message": "failed integrity check",
                            "path": ["currentUser", "dropCampaigns"],
                            "extensions": {"code": "IntegrityCheckFailed"},
                        }
                    ],
                }

        class MockRequestCtx:
            def __init__(self, response):
                self._response = response

            async def __aenter__(self):
                return self._response

            async def __aexit__(self, *args):
                return False

        twitch = Twitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace())
        auth = _AuthState(twitch)
        auth.access_token = "test-token"
        auth.user_id = 1234
        auth.session_id = "session-123"
        auth.device_id = "device-123"
        auth._logged_in.set()
        twitch._auth_state = auth
        auth.get_integrity_token = AsyncMock(return_value="mock_integrity")
        twitch.request = lambda method, url, **kwargs: MockRequestCtx(MockGQLResponse())

        with self.assertRaises(GQLException):
            await twitch.gql_request({"operationName": "ViewerDropsDashboard"})

    async def test_fetch_inventory_handles_empty_or_null_campaigns_safely(self):
        gui = SimpleNamespace(status=SimpleNamespace(update=Mock()), inv=SimpleNamespace(clear=Mock(), add=Mock()))
        twitch = Twitch(SimpleNamespace(dump=False), gui_factory=lambda _: gui)
        auth = _AuthState(twitch)
        auth.user_id = 1234
        twitch.get_auth = AsyncMock(return_value=auth)

        async def mock_gql(ops):
            if isinstance(ops, list):
                return []
            op_name = getattr(ops, "name", "")
            if op_name == "Inventory":
                return {
                    "data": {
                        "currentUser": {
                            "inventory": {
                                "dropCampaignsInProgress": [{"id": "ongoing_1"}],
                                "gameEventDrops": [],
                            }
                        }
                    }
                }
            elif op_name == "Campaigns":
                return {"data": {"currentUser": {"dropCampaigns": None}}}
            return {}

        twitch.gql_request = mock_gql
        # fetch_inventory should execute without crashing on dropCampaigns: None
        await twitch.fetch_inventory()


if __name__ == "__main__":
    unittest.main()
