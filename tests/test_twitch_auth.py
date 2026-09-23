import asyncio
import unittest
from types import SimpleNamespace

from core.constants import ClientType
from core.exceptions import LoginException
from network.twitch import Twitch, _AuthState


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


if __name__ == "__main__":
    unittest.main()
