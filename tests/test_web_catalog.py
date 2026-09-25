import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from core.constants import GQL_QUERIES
from core.exceptions import GQLException
from web.catalog import CATALOG_DETAIL_TTL, WebTwitch


def catalog_campaign():
    return {
        "twitch_id": "aa82829e-9f3c-4572-a120-39d2eb36729b",
        "name": "WARDOGS Beta & Launch",
        "status": "active",
        "account_link_url": "https://www.twitch.tv",
        "start_at": "2026-09-03T18:00:00Z",
        "end_at": "2026-09-30T17:59:59.999Z",
        "allow_is_enabled": True,
        "allowed_channels": [
            {"twitch_id": "123", "name": "streamer", "display_name": "Streamer"}
        ],
        "game": {
            "twitch_id": "743893402",
            "slug": "wardogs",
            "name": "WARDOGS",
            "display_name": "WARDOGS",
            "box_art_url": "/media/games/box_art/743893402.jpg",
        },
        "drops": [
            {
                "twitch_id": "2f7cc39d-a6f7-11f1-96ea-0a58a9feac02",
                "name": "WARDOG",
                "required_minutes_watched": 30,
                "start_at": "2026-09-03T18:00:00Z",
                "end_at": "2026-09-30T17:59:59.999Z",
                "benefits": [
                    {
                        "twitch_id": "9d0117a7-a62a-11f1-b5da-0a58a9feac02",
                        "name": "WARDOG",
                        "distribution_type": "BADGE",
                        "image_url": "/media/benefits/images/badge.png",
                    }
                ],
            }
        ],
    }


class WebCatalogTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_client_falls_back_without_changing_core_client(self):
        converted = WebTwitch._convert_campaign(catalog_campaign())
        campaign_id = converted["id"]
        client = WebTwitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace(print=lambda _: None))
        client._fetch_catalog = AsyncMock(return_value={campaign_id: converted})

        with patch(
            "network.twitch.Twitch.gql_request",
            new=AsyncMock(side_effect=GQLException([{"message": "failed integrity check"}])),
        ) as twitch_request:
            response = await client.gql_request(GQL_QUERIES["Campaigns"])
            await client.gql_request(GQL_QUERIES["Campaigns"])

        self.assertEqual(response["data"]["currentUser"]["dropCampaigns"][0]["id"], campaign_id)
        twitch_request.assert_awaited_once()
        self.assertEqual(
            (await client.fetch_campaigns([(campaign_id, {"id": campaign_id})]))[campaign_id][
                "timeBasedDrops"
            ][0]["requiredMinutesWatched"],
            30,
        )
        self.assertTrue(converted["game"]["boxArtURL"].startswith("https://"))

    def test_catalog_merge_keeps_twitch_inventory_values(self):
        client = WebTwitch(SimpleNamespace(), gui_factory=lambda _: SimpleNamespace())
        client._catalog_campaigns = {"active": {}}

        merged = client._merge_data(
            {
                "self": {"currentMinutesWatched": 10, "isClaimed": False},
                "allow": {"channels": [{"name": "Subroza"}]},
            },
            {
                "self": {"currentMinutesWatched": None},
                "allow": {"channels": [{"name": "VALORANT"}]},
                "name": "Campaign",
            },
        )

        self.assertEqual(merged["self"]["currentMinutesWatched"], 10)
        self.assertEqual(merged["allow"]["channels"], [{"name": "VALORANT"}])
        self.assertEqual(merged["name"], "Campaign")

    def test_active_channel_acl_bypasses_unchanged_cache_timestamp(self):
        client = WebTwitch(
            SimpleNamespace(priority=["WARDOGS"]),
            gui_factory=lambda _: SimpleNamespace(),
        )
        cached = {"updated_at": "same", "detail": {}}
        item = {
            "updated_at": "same",
            "status": "active",
            "allow_is_enabled": True,
            "game": {"display_name": "WARDOGS"},
        }

        self.assertFalse(client._reuse_cached_detail(item, cached))
        item["game"]["display_name"] = "Other game"
        self.assertTrue(client._reuse_cached_detail(item, cached))

    def test_cached_campaign_details_expire(self):
        now = 1_000_000

        self.assertFalse(WebTwitch._cache_expired({"fetched_at": now}, now))
        self.assertTrue(
            WebTwitch._cache_expired(
                {"fetched_at": now - CATALOG_DETAIL_TTL},
                now,
            )
        )


if __name__ == "__main__":
    unittest.main()
