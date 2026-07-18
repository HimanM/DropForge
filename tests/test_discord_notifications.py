import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from web.auth import AuthStore
from web.discord import DiscordNotifier, validate_webhook_url
from web.server import create_app


WEBHOOK = "https://discord.com/api/webhooks/123456789012345678/test_token"


def campaign(game_name: str = "Priority Game", drop_id: str = "drop-1") -> SimpleNamespace:
    game = SimpleNamespace(name=game_name)
    benefit = SimpleNamespace(
        name="Reward One",
        image_url="https://static-cdn.jtvnw.net/reward.png",
    )
    drop = SimpleNamespace(
        id=drop_id,
        name="Reward Drop",
        benefits=[benefit],
        required_minutes=60,
        ends_at=datetime.now(timezone.utc) + timedelta(days=1),
        is_claimed=False,
    )
    item = SimpleNamespace(
        id=f"campaign-{drop_id}",
        name="Priority Campaign",
        game=game,
        drops=[drop],
        image_url="https://static-cdn.jtvnw.net/category.jpg",
        link_url="https://www.twitch.tv/drops/campaigns",
        ends_at=datetime.now(timezone.utc) + timedelta(days=1),
        claimed_drops=1,
        total_drops=2,
        finished=False,
        can_earn_within=lambda _: True,
    )
    drop.campaign = item
    return item


class DiscordNotificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = AuthStore(Path(self.temp.name, "auth.sqlite3"))
        self.notifier = DiscordNotifier(self.store)
        self.notifier.update({"webhook_url": WEBHOOK, "enabled": True})
        self.payloads = []
        self.notifier._schedule = self.payloads.append  # type: ignore[method-assign]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_url_is_restricted_and_secret_is_not_returned(self) -> None:
        self.assertEqual(validate_webhook_url(WEBHOOK), WEBHOOK)
        with self.assertRaises(ValueError):
            validate_webhook_url("https://discord.com.evil.example/api/webhooks/1/token")
        with self.assertRaises(ValueError):
            validate_webhook_url(f"{WEBHOOK}?redirect=https://example.com")
        snapshot = self.notifier.snapshot()
        self.assertTrue(snapshot["configured"])
        self.assertNotIn("url", snapshot)
        self.assertNotIn("test_token", str(snapshot))
        self.assertTrue(DiscordNotifier(AuthStore(self.store.path)).snapshot()["configured"])

    def test_priority_drop_messages_include_category_and_reward_images(self) -> None:
        self.notifier.finish_inventory()
        ignored = campaign("Ignored Game", "ignored")
        selected = campaign()

        self.notifier.observe_campaign(ignored, ["Priority Game"])
        self.notifier.observe_campaign(selected, ["Priority Game"])
        self.assertEqual(len(self.payloads), 1)
        message = self.payloads[0]
        self.assertEqual(message["allowed_mentions"], {"parse": []})
        self.assertEqual(message["embeds"][0]["image"]["url"], selected.image_url)
        self.assertEqual(
            message["embeds"][1]["thumbnail"]["url"],
            selected.drops[0].benefits[0].image_url,
        )

        selected.drops[0].is_claimed = True
        self.notifier.drop_updated(selected.drops[0], ["Priority Game"])
        self.notifier.drop_updated(selected.drops[0], ["Priority Game"])
        self.assertEqual([payload["embeds"][0]["title"] for payload in self.payloads], [
            "New priority Drops detected",
            "Drop claimed",
        ])

    def test_idle_reason_is_deduplicated_and_recovery_is_reported(self) -> None:
        selected = campaign()
        channel = SimpleNamespace(
            id=7,
            name="Streamer",
            game=selected.game,
            online=True,
            drops_enabled=False,
        )
        manager = SimpleNamespace(
            _twitch=SimpleNamespace(
                settings=SimpleNamespace(priority=["Priority Game"]),
                channels={channel.id: channel},
            ),
            inv=SimpleNamespace(campaigns={selected.id: selected}),
        )

        self.notifier.idle(manager)
        self.notifier.idle(manager)
        channel.drops_enabled = True
        self.notifier.watching(manager, channel)

        self.assertEqual([payload["embeds"][0]["title"] for payload in self.payloads], [
            "Drops disabled on live channels",
            "Mining resumed",
        ])


class DiscordNotificationApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_update_never_returns_the_webhook_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            auth_path = Path(directory, "auth.sqlite3")
            AuthStore(auth_path).provision(
                "correct horse battery", "recovery-code-long-enough"
            )
            app = create_app(auth_path, Path(directory), auto_start=False)
            async with TestClient(TestServer(app)) as client:
                login = await client.post(
                    "/api/login", json={"password": "correct horse battery"}
                )
                csrf = (await login.json())["csrf_token"]
                response = await client.put(
                    "/api/notifications",
                    headers={"X-CSRF-Token": csrf},
                    json={"webhook_url": WEBHOOK, "enabled": True},
                )
                body = await response.json()

                self.assertEqual(response.status, 200)
                self.assertNotIn("test_token", str(body))


if __name__ == "__main__":
    unittest.main()
