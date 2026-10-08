import base64
import json
import unittest
from collections import OrderedDict
from time import monotonic
from types import SimpleNamespace

from yarl import URL

from models.channel import Channel, Stream


class _Response:
    def __init__(self, status=204, body=""):
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def text(self):
        return self.body


class ChannelWatchTest(unittest.IsolatedAsyncioTestCase):
    def test_trusted_acl_campaign_is_accepted_when_available_drops_omits_it(self):
        channel = object.__new__(Channel)
        channel.id = 456
        channel.acl_based = True

        ewc = SimpleNamespace(
            id="ewc",
            allowed_channels=[channel],
            can_earn=lambda *_args, **_kwargs: False,
        )
        rainbow_six = SimpleNamespace(
            id="rainbow-six",
            allowed_channels=[channel],
            can_earn=lambda candidate, **kwargs: (
                candidate is channel and kwargs["ignore_channel_status"]
            ),
        )
        channel._twitch = SimpleNamespace(
            _campaigns={ewc.id: ewc, rainbow_six.id: rainbow_six},
            settings=SimpleNamespace(trust_allowed_channels=False),
        )

        self.assertFalse(channel._check_drops_enabled([{"id": ewc.id}]))
        channel._twitch.settings.trust_allowed_channels = True
        self.assertTrue(channel._check_drops_enabled([{"id": ewc.id}]))

    async def test_send_watch_requests_each_new_segment_once(self):
        twitch = SimpleNamespace(_auth_state=SimpleNamespace(user_id="789"))
        media = "#EXTM3U\n#EXTINF:2.0,\none.ts\n#EXTINF:2.0,\ntwo.ts\n"
        requests = []

        def request(method, url, **kwargs):
            requests.append((method, str(url), kwargs))
            return _Response(200, media) if method == "GET" else _Response(200)

        twitch.request = request

        channel = object.__new__(Channel)
        channel._twitch = twitch
        channel.id = 456
        channel._login = "streamer"
        channel._spade_url = URL("https://spade.twitch.tv/track")
        channel._watch_broadcast_id = None
        channel._watched_segments = OrderedDict()
        channel._last_spade_sent = monotonic()

        stream = object.__new__(Stream)
        stream.channel = channel
        stream.broadcast_id = 123
        stream.game = None
        stream._stream_url = URL("https://video.example/live/index.m3u8")
        channel._stream = stream
        twitch.watching_channel = SimpleNamespace(
            get_with_default=lambda _default: channel
        )

        self.assertTrue(await channel.send_watch())
        self.assertTrue(await channel.send_watch())
        head_urls = [url for method, url, _kwargs in requests if method == "HEAD"]
        self.assertEqual(
            head_urls,
            ["https://video.example/live/one.ts", "https://video.example/live/two.ts"],
        )

    async def test_spade_telemetry_keeps_current_watch_payload(self):
        twitch = SimpleNamespace(_auth_state=SimpleNamespace(user_id="789"))
        twitch.request = lambda *args, **kwargs: (
            setattr(twitch, "request_args", (args, kwargs)) or _Response()
        )
        channel = object.__new__(Channel)
        channel._twitch = twitch
        channel.id = 456
        channel._login = "streamer"
        channel._spade_url = URL("https://spade.twitch.tv/track")
        stream = object.__new__(Stream)
        stream.channel = channel
        stream.broadcast_id = 123
        stream.game = None
        channel._stream = stream
        twitch.watching_channel = SimpleNamespace(get_with_default=lambda _default: channel)

        self.assertTrue(await channel._send_watch_spade())
        args, kwargs = twitch.request_args
        self.assertEqual(args[:2], ("POST", channel._spade_url))
        properties = json.loads(base64.b64decode(kwargs["data"]["data"]))[0]["properties"]
        self.assertEqual(properties["minutes_logged"], 1)
        self.assertIn("client_time", properties)

    def test_playlist_parser_rejects_unassociated_or_credentialed_urls(self):
        base = URL("https://video.example/live/index.m3u8")
        self.assertEqual(Stream.playlist_urls("#EXTM3U\nsegment.ts", base), [])
        self.assertEqual(
            Stream.playlist_urls("#EXTM3U\n#EXTINF:2,\nhttps://user@evil.example/a.ts", base),
            [],
        )


if __name__ == "__main__":
    unittest.main()
