import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import web
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
        is_earned=False,
        is_free_badge=False,
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
        completed_drops=1,
        total_drops=2,
        finished=False,
        has_free_badge=False,
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

    def test_auth_alert_persists_and_is_deduplicated_until_recovery(self) -> None:
        self.notifier.auth_issue("expired", "Twitch session expired. Activate again.")
        self.notifier.auth_issue("expired", "Twitch session expired. Activate again.")
        self.assertEqual(len(self.payloads), 1)
        alert = DiscordNotifier(self.store).auth_alert()
        self.assertTrue(alert["requires_login"])
        self.assertTrue(alert["notified"])
        embed = self.payloads[0]["embeds"][0]
        self.assertEqual(embed["title"], "Twitch login required")
        self.assertEqual(embed["footer"]["text"], "DropForge | Authentication")
        restarted = DiscordNotifier(self.store)
        restarted._schedule = self.payloads.append
        restarted.auth_issue("expired", "Twitch session expired. Activate again.")
        self.assertEqual(len(self.payloads), 1)
        restarted.auth_recovered()
        self.assertEqual(restarted.auth_alert(), {})
        self.assertEqual(len(self.payloads), 2)
        restarted.auth_issue("expired", "Another session expired.")
        self.assertEqual(len(self.payloads), 3)

    def test_auth_alert_opt_out_keeps_web_warning_without_discord(self) -> None:
        self.notifier.update({"notify_auth": False})
        self.notifier.auth_issue("expired", "Activate again.")
        self.assertEqual(len(self.payloads), 0)
        self.assertTrue(self.notifier.auth_alert()["requires_login"])
        self.notifier.update({"notify_auth": True})
        self.assertEqual(len(self.payloads), 1)

    def test_brief_connection_warning_does_not_send_recovery_spam(self) -> None:
        self.notifier.auth_issue("connection", "Retrying authorization.", requires_login=False, notify=False)
        self.assertFalse(self.notifier.auth_alert()["requires_login"])
        self.notifier.auth_recovered()
        self.assertEqual(len(self.payloads), 0)

    def test_connection_warning_does_not_replace_required_login(self) -> None:
        self.notifier.auth_issue("expired", "Activate again.")
        self.notifier.auth_issue("connection", "Retrying authorization.", requires_login=False)
        self.assertEqual(self.notifier.auth_alert()["kind"], "expired")
        self.assertEqual(len(self.payloads), 1)

    def test_pending_claim_is_not_reported_as_confirmed_delivery(self) -> None:
        selected = campaign()
        selected._twitch = SimpleNamespace(pending_claims=SimpleNamespace(pending=lambda _: True))
        drop = selected.drops[0]
        drop.is_claimed = True
        drop.is_earned = True
        self.notifier.drop_updated(drop, ["Priority Game"])
        message = self.payloads[0]["embeds"][0]
        self.assertEqual(message["title"], "Drop earned")
        self.assertIn("awaiting Twitch confirmation", str(message["fields"]))
        restarted = DiscordNotifier(self.store)
        restarted._schedule = self.payloads.append
        restarted.drop_updated(drop, ["Priority Game"])
        self.assertEqual(len(self.payloads), 1)

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
        self.assertEqual(message["embeds"][0]["thumbnail"]["url"], selected.image_url)
        self.assertEqual(
            message["embeds"][1]["image"]["url"],
            selected.drops[0].benefits[0].image_url,
        )
        self.assertEqual(message["embeds"][1]["thumbnail"]["url"], selected.image_url)

        selected.drops[0].is_claimed = True
        self.notifier.drop_updated(selected.drops[0], ["Priority Game"])
        self.notifier.drop_updated(selected.drops[0], ["Priority Game"])
        self.assertEqual([payload["embeds"][0]["title"] for payload in self.payloads], [
            "New priority Drops detected",
            "Drop claimed",
        ])
        earned = self.payloads[-1]["embeds"][0]
        self.assertEqual(earned["image"]["url"], selected.drops[0].benefits[0].image_url)
        self.assertIn(selected.drops[0].benefits[0].image_url, str(earned["fields"]))

    def test_earned_unclaimed_drop_sends_completion_message(self) -> None:
        selected = campaign()
        selected.drops[0].is_earned = True

        self.notifier.drop_updated(selected.drops[0], ["Priority Game"])

        message = self.payloads[0]["embeds"][0]
        self.assertEqual(message["title"], "Drop earned")
        self.assertEqual(message["fields"][-1]["name"], "Delivery")

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

    def test_badge_events_use_priority_filter_and_badge_formatting(self) -> None:
        selected = campaign()
        selected.has_free_badge = True
        selected.drops[0].is_free_badge = True
        manager = SimpleNamespace(
            _twitch=SimpleNamespace(settings=SimpleNamespace(priority=["Priority Game"])),
            inv=SimpleNamespace(campaigns={selected.id: selected}),
        )

        self.notifier.badge_farming_started(manager, [selected.game])
        selected.drops[0].is_claimed = True
        self.notifier.drop_updated(selected.drops[0], ["Priority Game"])

        self.assertEqual([payload["embeds"][0]["title"] for payload in self.payloads], [
            "Free badge fallback active",
            "Free badge earned",
        ])

    def test_operational_events_are_deduplicated(self) -> None:
        self.notifier.update({"notify_operational": True})

        self.notifier.operational("Miner restarting", "Retrying", event_key="restart")
        self.notifier.operational("Miner restarting", "Retrying", event_key="restart")

        self.assertEqual(len(self.payloads), 1)

    def test_auto_badges_notify_outside_priority_without_item_spam(self) -> None:
        selected = campaign("Badge Game", "free-watch-badge")
        drop = selected.drops[0]
        drop.is_free_badge = True
        drop.is_claimed = True
        self.notifier.drop_updated(drop, [])
        self.assertEqual(self.payloads, [])
        self.notifier.drop_updated(drop, [], auto_farm_badges=True)
        self.notifier.drop_updated(drop, [], auto_farm_badges=True)
        other = campaign("Badge Game", "subscription-or-item").drops[0]
        other.is_claimed = True
        self.notifier.drop_updated(other, [], auto_farm_badges=True)
        self.assertEqual(len(self.payloads), 1)
        self.assertEqual(self.payloads[0]["embeds"][0]["title"], "Free badge earned")
        self.assertEqual(self.payloads[0]["embeds"][0]["footer"]["text"], "DropForge | Free badges")
        restarted = DiscordNotifier(self.store)
        restarted._schedule = self.payloads.append
        restarted.drop_updated(drop, [], auto_farm_badges=True)
        self.assertEqual(len(self.payloads), 1)

    def test_auto_badge_start_includes_non_priority_categories_and_respects_opt_out(self) -> None:
        selected = campaign("Badge Game")
        selected.has_free_badge = True
        manager = SimpleNamespace(
            _twitch=SimpleNamespace(settings=SimpleNamespace(priority=[], auto_farm_badges=True)),
            inv=SimpleNamespace(campaigns={selected.id: selected}),
        )
        self.notifier.badge_farming_started(manager, [selected.game])
        self.assertEqual(len(self.payloads), 1)
        self.assertIn("Badge Game", str(self.payloads[0]["embeds"][0]["fields"]))
        self.notifier.update({"notify_claimed": False})
        selected.drops[0].is_free_badge = True
        selected.drops[0].is_claimed = True
        self.notifier.drop_updated(selected.drops[0], [], auto_farm_badges=True)
        self.assertEqual(len(self.payloads), 1)


class DiscordNotificationApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_artwork_is_uploaded_and_embedded_with_rate_limit_retry(self) -> None:
        received = []

        async def webhook(request):
            reader = await request.multipart()
            parts = {}
            while (part := await reader.next()) is not None:
                parts[part.name] = bytes(await part.read())
            received.append(parts)
            if len(received) == 1:
                return web.json_response({"retry_after": 0}, status=429)
            return web.json_response({"id": "message"})

        app = web.Application()
        app.router.add_post("/webhook", webhook)
        with tempfile.TemporaryDirectory() as directory:
            notifier = DiscordNotifier(AuthStore(Path(directory, "auth.sqlite3")))
            drop = campaign().drops[0]
            payload = notifier._claimed_payload(drop)
            art = b"test PNG bytes"
            with patch.object(notifier, "_download_image", AsyncMock(return_value=("png", "image/png", art))) as download:
                async with TestServer(app) as server:
                    await notifier._post(str(server.make_url("/webhook")), payload)
            self.assertEqual(download.await_count, 2)
            self.assertEqual(len(received), 2)
            for parts in received:
                embed = json.loads(parts["payload_json"])["embeds"][0]
                self.assertEqual(embed["image"]["url"], "attachment://artwork-0.png")
                self.assertEqual(embed["thumbnail"]["url"], "attachment://artwork-1.png")
                self.assertEqual(parts["files[0]"], art)
                self.assertEqual(parts["files[1]"], art)
            self.assertEqual(payload["embeds"][0]["image"]["url"], drop.benefits[0].image_url)

    async def test_artwork_duplicates_are_reused_and_failures_keep_remote_embed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            notifier = DiscordNotifier(AuthStore(Path(directory, "auth.sqlite3")))
            payload = notifier._new_drops_payload(campaign(), [campaign().drops[0]] * 9)
            with patch.object(notifier, "_download_image", AsyncMock(return_value=None)) as download:
                prepared, files = await notifier._attach_images(None, payload)
            self.assertEqual(download.await_count, 2)
            self.assertEqual(prepared, payload)
            self.assertEqual(files, [])
            with patch.object(notifier, "_download_image", AsyncMock(return_value=("png", "image/png", b"art"))):
                prepared, files = await notifier._attach_images(None, payload)
            self.assertEqual(len(files), 2)
            self.assertTrue(all(embed["image"]["url"] == "attachment://artwork-0.png"
                                for embed in prepared["embeds"][1:]))

    async def test_artwork_download_is_bounded_and_restricted(self) -> None:
        session = MagicMock()
        for url in ("http://static-cdn.jtvnw.net/a.png", "https://127.0.0.1/a.png",
                    "https://static-cdn.jtvnw.net.evil.test/a.png", "https://static-cdn.jtvnw.net:443/a.png"):
            self.assertIsNone(await DiscordNotifier._download_image(session, url))
        session.get.assert_not_called()
        response = MagicMock(status=200, content_type="image/png")
        session.get.return_value.__aenter__ = AsyncMock(return_value=response)
        session.get.return_value.__aexit__ = AsyncMock(return_value=False)

        async def chunks(size):
            yield b"a" * size

        url = "https://static-cdn.jtvnw.net/reward.png"
        response.content.iter_chunked.side_effect = lambda _: chunks(32)
        self.assertEqual(await DiscordNotifier._download_image(session, url), ("png", "image/png", b"a" * 32))
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
        response.content.iter_chunked.side_effect = lambda _: chunks(512 * 1024 + 1)
        self.assertIsNone(await DiscordNotifier._download_image(session, url))
        response.status = 302
        self.assertIsNone(await DiscordNotifier._download_image(session, url))
        response.status, response.content_type = 200, "text/html"
        self.assertIsNone(await DiscordNotifier._download_image(session, url))

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
