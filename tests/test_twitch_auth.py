import asyncio
import unittest
from types import SimpleNamespace

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from yarl import URL

from core.constants import ClientType
from core.exceptions import LoginException
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


class TwitchTokenImportAsyncTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_validate_auth_token_falls_back_to_inventory_on_campaign_gql_error(self):
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
                post_calls.append(json.get("operationName"))

                class Resp:
                    status = 200

                    async def __aenter__(self):
                        return self

                    async def __aexit__(self, *_args):
                        pass

                    async def json(self):
                        if post_calls[-1] == "ViewerDropsDashboard":
                            return {"errors": [{"message": "PersistedQueryNotFound"}]}
                        return {
                            "data": {"currentUser": {"inventory": {"dropCampaignsInProgress": [{"id": "c1"}]}}}
                        }

                return Resp()

        with patch("aiohttp.ClientSession", MockSession):
            client, user_id, count = await validate_auth_token("valid_token_value_here_12345")
            self.assertIs(client, ClientType.WEB)
            self.assertEqual(user_id, 55555)
            self.assertEqual(count, 1)
            self.assertEqual(post_calls, ["ViewerDropsDashboard", "Inventory"])

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

    async def test_import_auth_token_saves_cookies_for_both_web_and_mobile(self):
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


if __name__ == "__main__":
    unittest.main()
