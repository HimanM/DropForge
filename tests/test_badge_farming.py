import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from core.constants import State
from models.inventory import DropsCampaign
from network.twitch import Twitch


def _stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _drop(drop_id: str, distribution: str, minutes: int) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "id": drop_id,
        "name": drop_id,
        "benefitEdges": [{"benefit": {
            "id": f"benefit-{drop_id}",
            "name": drop_id,
            "distributionType": distribution,
            "imageAssetURL": "https://example.test/reward.png",
        }}],
        "startAt": _stamp(now - timedelta(hours=1)),
        "endAt": _stamp(now + timedelta(days=1)),
        "requiredMinutesWatched": minutes,
        "preconditionDrops": [],
    }


def _campaign(twitch: SimpleNamespace) -> DropsCampaign:
    now = datetime.now(timezone.utc)
    return DropsCampaign(twitch, {
        "id": "campaign",
        "name": "Mixed badge campaign",
        "game": {
            "id": "1",
            "name": "Badge Game",
            "boxArtURL": "https://example.test/game-285x380.jpg",
        },
        "self": {"isAccountConnected": True},
        "accountLinkURL": "https://example.test/link",
        "startAt": _stamp(now - timedelta(hours=1)),
        "endAt": _stamp(now + timedelta(days=1)),
        "status": "ACTIVE",
        "allow": {"isEnabled": False, "channels": []},
        "timeBasedDrops": [
            _drop("watch-badge", "BADGE", 60),
            _drop("subscription-badge", "BADGE", 0),
            _drop("item", "DIRECT_ENTITLEMENT", 30),
        ],
    }, {})


class BadgeFarmingTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = SimpleNamespace(
            enable_badges_emotes=True,
            farm_unlinked=False,
            priority_mode=None,
            priority=[],
            completed_badges=set(),
        )
        self.twitch = SimpleNamespace(
            settings=settings,
            badge_farming=False,
            gui=SimpleNamespace(
                inv=SimpleNamespace(update_drop=lambda drop: None),
                display_drop=lambda *args, **kwargs: None,
            ),
            mark_badge_complete=lambda drop: setattr(drop, "is_claimed", True),
        )

    def test_auto_mode_selects_watch_badge_not_subscription_or_item(self) -> None:
        campaign = _campaign(self.twitch)
        watch = campaign.get_drop("watch-badge")
        subscription = campaign.get_drop("subscription-badge")
        item = campaign.get_drop("item")
        assert watch is not None and subscription is not None and item is not None

        self.assertTrue(watch.is_free_badge)
        self.assertFalse(subscription.is_free_badge)
        self.assertFalse(item.is_free_badge)
        self.twitch.badge_farming = True
        self.assertIs(campaign.first_drop, watch)
        self.assertFalse(subscription.can_earn())
        self.assertFalse(item.can_earn())

    def test_completed_badge_ledger_prevents_refarming(self) -> None:
        self.twitch.settings.completed_badges.add("watch-badge")
        campaign = _campaign(self.twitch)
        watch = campaign.get_drop("watch-badge")
        assert watch is not None
        self.assertTrue(watch.is_claimed)

    def test_verified_watch_completion_stops_farming_without_claim(self) -> None:
        campaign = _campaign(self.twitch)
        item = campaign.get_drop("item")
        assert item is not None

        item.update_minutes(30)
        item.extra_current_minutes = 15

        self.assertTrue(item.is_earned)
        self.assertEqual(item.current_minutes, 30)
        self.assertFalse(item.can_earn())

    def test_mark_badge_complete_persists_and_refreshes_inventory(self) -> None:
        campaign = _campaign(self.twitch)
        watch = campaign.get_drop("watch-badge")
        assert watch is not None
        calls: list[object] = []
        settings = SimpleNamespace(
            completed_badges=set(),
            alter=lambda: calls.append("alter"),
            save=lambda: calls.append("save"),
        )
        owner = SimpleNamespace(
            settings=settings,
            change_state=lambda state: calls.append(state),
            print=lambda message: calls.append(message),
        )

        Twitch.mark_badge_complete(owner, watch)

        self.assertTrue(watch.is_claimed)
        self.assertEqual(settings.completed_badges, {"watch-badge"})
        self.assertEqual(calls, [
            "alter",
            "save",
            "Free badge completed: watch-badge (Badge Game)",
            State.INVENTORY_FETCH,
        ])

    def test_idle_fallback_is_default_off_and_starts_only_once(self) -> None:
        states: list[State] = []
        messages: list[str] = []
        owner = SimpleNamespace(
            settings=SimpleNamespace(auto_farm_badges=False),
            badge_farming=False,
            change_state=states.append,
            print=messages.append,
        )

        self.assertFalse(Twitch._try_badge_fallback(owner))
        owner.settings.auto_farm_badges = True
        self.assertTrue(Twitch._try_badge_fallback(owner))
        self.assertFalse(Twitch._try_badge_fallback(owner))
        self.assertEqual(states, [State.GAMES_UPDATE])
        self.assertEqual(messages, [
            "Priority work is idle; checking free watch-time badges."
        ])


if __name__ == "__main__":
    unittest.main()
