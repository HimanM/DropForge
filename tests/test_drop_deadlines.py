import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from core.constants import State
from core.settings import default_settings
from network.twitch import Twitch
from test_badge_farming import _campaign


class DropDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.settings = SimpleNamespace(enable_badges_emotes=True, farm_unlinked=False,
            priority_mode=None, priority=[], completed_badges=set(), skip_unfinishable_drops=True)
        self.twitch = SimpleNamespace(settings=self.settings, badge_farming=False,
            gui=SimpleNamespace(inv=SimpleNamespace(update_drop=lambda _: None)))
        self.campaign = _campaign(self.twitch)
        self.drop = self.campaign.get_drop("item")

    def test_default_off_preserves_existing_selection(self):
        self.assertFalse(default_settings["skip_unfinishable_drops"])
        self.settings.skip_unfinishable_drops = False
        self.drop.ends_at = self.now + timedelta(minutes=1)
        self.assertTrue(self.drop.can_earn())
        self.settings.skip_unfinishable_drops = True
        self.assertFalse(self.drop.can_earn())

    def test_uses_remaining_item_time_not_full_requirement(self):
        self.drop.ends_at = self.now + timedelta(minutes=15)
        self.drop.real_current_minutes = 20
        self.assertTrue(self.drop.can_earn())
        self.drop.real_current_minutes = 10
        self.assertFalse(self.drop.can_earn())

    def test_campaign_deadline_can_be_earlier_than_item_deadline(self):
        self.campaign.ends_at = self.now + timedelta(minutes=10)
        self.assertFalse(self.drop.can_finish)

    def test_equal_time_is_allowed_and_future_start_reduces_the_window(self):
        with patch("models.inventory.datetime") as clock:
            clock.now.return_value = self.now
            self.drop.ends_at = self.now + timedelta(minutes=30)
            self.assertTrue(self.drop.can_finish)
            self.drop.starts_at = self.now + timedelta(minutes=1)
            self.assertFalse(self.drop.can_finish)

    def test_unfinishable_item_does_not_hide_another_earnable_reward(self):
        self.drop.ends_at = self.now + timedelta(minutes=1)
        badge = self.campaign.get_drop("watch-badge")
        self.assertFalse(self.drop.can_earn())
        self.assertIs(self.campaign.first_drop, badge)
        self.assertTrue(self.campaign.can_earn())

    def test_completed_reward_can_still_be_claimed(self):
        self.drop.claim_id = "test-claim"
        self.drop.real_current_minutes = self.drop.required_minutes
        self.drop.ends_at = self.now - timedelta(minutes=1)
        self.assertTrue(self.drop.can_claim)


class DeadlineSwitchTests(unittest.IsolatedAsyncioTestCase):
    async def test_running_watch_loop_switches_before_another_watch_request(self):
        channel = SimpleNamespace(online=True, name="TestChannel", send_watch=AsyncMock())
        client = SimpleNamespace(settings=SimpleNamespace(skip_unfinishable_drops=True),
            watching_channel=SimpleNamespace(get=AsyncMock(side_effect=[channel, asyncio.CancelledError()])),
            can_watch=Mock(return_value=False), stop_watching=Mock(), change_state=Mock(), print=Mock())
        with self.assertRaises(asyncio.CancelledError):
            await Twitch._watch_loop.__wrapped__(client)
        channel.send_watch.assert_not_awaited()
        client.stop_watching.assert_called_once()
        client.change_state.assert_called_once_with(State.GAMES_UPDATE)
