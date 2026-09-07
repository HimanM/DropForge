import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.constants import GQLPersistedQuery
from network.twitch import Twitch


class AsyncContext:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class PersistedQueryRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_until_persisted_query_recovers(self) -> None:
        twitch = object.__new__(Twitch)
        twitch._qgl_limiter = AsyncContext()
        twitch._client_type = SimpleNamespace(USER_AGENT="test")
        twitch.get_auth = AsyncMock(
            return_value=SimpleNamespace(headers=lambda **_kwargs: {})
        )
        twitch.print = Mock()
        replies = iter([
            {
                "errors": [{"message": "PersistedQueryNotFound"}],
                "extensions": {"operationName": "Inventory"},
            },
            {
                "errors": [{"message": "PersistedQueryNotFound"}],
                "extensions": {"operationName": "Inventory"},
            },
            {"data": {"currentUser": {}}},
        ])
        requests = []

        @asynccontextmanager
        async def request(*_args, **kwargs):
            requests.append(kwargs)
            yield SimpleNamespace(json=AsyncMock(return_value=next(replies)))

        twitch.request = request
        query = GQLPersistedQuery("Inventory", "0" * 64)
        with (
            patch("network.twitch.PERSISTED_QUERY_WARNING_AFTER", 0),
            patch("network.twitch.asyncio.sleep", new=AsyncMock()),
        ):
            result = await twitch.gql_request(query)

        self.assertEqual(result, {"data": {"currentUser": {}}})
        self.assertNotIn("Connection", requests[0]["headers"])
        self.assertEqual(requests[1]["headers"]["Connection"], "close")
        twitch.print.assert_called_once()


if __name__ == "__main__":
    unittest.main()
