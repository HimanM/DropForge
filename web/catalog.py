from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

import aiohttp
from yarl import URL

from core.constants import CACHE_PATH, GQL_QUERIES, JsonType
from core.exceptions import GQLException
from core.utils import chunk, json_load, json_save
from network.twitch import Twitch


logger = logging.getLogger("TwitchDrops")
CATALOG_ORIGIN = URL("https://ttvdrops.lovinator.space")
CATALOG_CACHE = CACHE_PATH / "campaign-catalog.json"


class WebTwitch(Twitch):
    """Web-only Twitch client with public campaign discovery fallback."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._catalog_campaigns: dict[str, JsonType] = {}

    @staticmethod
    def _asset_url(value: str) -> str:
        return str(CATALOG_ORIGIN.join(URL(value))) if value else ""

    @classmethod
    def _convert_campaign(cls, data: JsonType) -> JsonType:
        game = data["game"]
        link_url = str(data.get("account_link_url") or "")
        link_host = URL(link_url).host or ""
        return {
            "id": data["twitch_id"],
            "name": data["name"],
            "game": {
                "id": game["twitch_id"],
                "name": game["name"],
                "displayName": game.get("display_name") or game["name"],
                "slug": game["slug"],
                "boxArtURL": cls._asset_url(str(game.get("box_art_url") or "")),
            },
            "self": {
                # The catalogue cannot verify external game-account connections.
                "isAccountConnected": not link_host or link_host.endswith("twitch.tv")
            },
            "accountLinkURL": link_url,
            "startAt": data["start_at"],
            "endAt": data["end_at"],
            "status": str(data.get("status") or "active").upper(),
            "allow": {
                "isEnabled": bool(data.get("allow_is_enabled")),
                "channels": [
                    {
                        "id": channel["twitch_id"],
                        "name": channel["name"],
                        "displayName": channel.get("display_name") or channel["name"],
                    }
                    for channel in data.get("allowed_channels") or []
                ],
            },
            "timeBasedDrops": [
                {
                    "id": drop["twitch_id"],
                    "name": drop["name"],
                    "startAt": drop.get("start_at") or data["start_at"],
                    "endAt": drop.get("end_at") or data["end_at"],
                    "requiredMinutesWatched": drop.get("required_minutes_watched") or 0,
                    "preconditionDrops": [],
                    "benefitEdges": [
                        {
                            "benefit": {
                                "id": benefit["twitch_id"],
                                "name": benefit["name"],
                                "distributionType": benefit.get("distribution_type") or "UNKNOWN",
                                "imageAssetURL": cls._asset_url(
                                    str(benefit.get("image_url") or "")
                                ),
                            }
                        }
                        for benefit in drop.get("benefits") or []
                    ],
                }
                for drop in data["drops"]
            ],
        }

    async def _fetch_catalog(self) -> dict[str, JsonType]:
        try:
            cache: JsonType = json_load(
                CATALOG_CACHE, {"version": 1, "campaigns": {}}, merge=False
            )
        except (OSError, ValueError, json.JSONDecodeError):
            cache = {"version": 1, "campaigns": {}}
        cached = cache.get("campaigns") if isinstance(cache, dict) else {}
        if not isinstance(cached, dict):
            cached = {}

        try:
            items: list[JsonType] = []
            list_url = CATALOG_ORIGIN / "api/v1/twitch/campaigns/"
            for status in ("active", "upcoming"):
                async with self.request(
                    "GET",
                    list_url.with_query(status=status, page_size=500),
                    headers={"Accept": "application/json"},
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"campaign catalogue HTTP {response.status}")
                    payload = await response.json()
                page_items = payload.get("items") if isinstance(payload, dict) else None
                if not isinstance(page_items, list) or len(page_items) > 500:
                    raise RuntimeError("campaign catalogue returned an invalid list")
                items.extend(item for item in page_items if isinstance(item, dict))

            current: dict[str, JsonType] = {}
            changed: list[tuple[str, str]] = []
            for item in items:
                campaign_id = str(item.get("twitch_id") or "")
                try:
                    UUID(campaign_id)
                except ValueError:
                    continue
                if not item.get("is_fully_imported"):
                    continue
                updated_at = str(item.get("updated_at") or "")
                cached_item = cached.get(campaign_id)
                if isinstance(cached_item, dict) and isinstance(cached_item.get("detail"), dict):
                    current[campaign_id] = cached_item
                    if cached_item.get("updated_at") == updated_at:
                        continue
                changed.append((campaign_id, updated_at))

            async def fetch_detail(campaign_id: str, updated_at: str) -> tuple[str, JsonType]:
                url = CATALOG_ORIGIN / f"api/v1/twitch/campaigns/{campaign_id}/"
                async with self.request("GET", url, headers={"Accept": "application/json"}) as response:
                    if response.status != 200:
                        raise RuntimeError(f"campaign catalogue detail HTTP {response.status}")
                    detail = await response.json()
                if not isinstance(detail, dict) or detail.get("twitch_id") != campaign_id:
                    raise RuntimeError("campaign catalogue returned invalid campaign details")
                return campaign_id, {"updated_at": updated_at, "detail": detail}

            for entries in chunk(changed, 10):
                results = await asyncio.gather(
                    *(fetch_detail(*entry) for entry in entries), return_exceptions=True
                )
                for result in results:
                    if isinstance(result, asyncio.CancelledError):
                        raise result
                    if isinstance(result, BaseException):
                        logger.warning("Unable to refresh a public campaign: %s", result)
                    else:
                        campaign_id, cached_item = result
                        current[campaign_id] = cached_item

            CATALOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
            json_save(CATALOG_CACHE, {"version": 1, "campaigns": current}, sort=True)
            cached = current
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, OSError, ValueError) as exc:
            logger.warning("Public campaign catalogue unavailable; using cache: %s", exc)

        campaigns: dict[str, JsonType] = {}
        for campaign_id, item in cached.items():
            try:
                campaign = self._convert_campaign(item["detail"])
                if campaign["timeBasedDrops"]:
                    campaigns[campaign_id] = campaign
            except (KeyError, TypeError, ValueError):
                logger.warning("Ignoring invalid cached campaign %s", campaign_id)
        return campaigns

    async def gql_request(self, ops):
        is_campaign_list = (
            isinstance(ops, dict)
            and ops.get("operationName") == GQL_QUERIES["Campaigns"].get("operationName")
        )
        if not is_campaign_list:
            return await super().gql_request(ops)

        original_error: GQLException | None = None
        try:
            response = await super().gql_request(ops)
            campaigns = ((response.get("data") or {}).get("currentUser") or {}).get(
                "dropCampaigns"
            )
            if campaigns:
                self._catalog_campaigns.clear()
                return response
        except GQLException as exc:
            if "IntegrityCheckFailed" not in str(exc) and "failed integrity check" not in str(exc):
                raise
            original_error = exc

        self._catalog_campaigns = await self._fetch_catalog()
        if not self._catalog_campaigns:
            if original_error is not None:
                raise original_error
            return response
        self.print(
            f"Loaded {len(self._catalog_campaigns)} campaigns from the public catalogue; "
            "Twitch inventory remains authoritative for account progress."
        )
        return {
            "data": {
                "currentUser": {
                    "dropCampaigns": [
                        {"id": campaign_id, "status": data["status"]}
                        for campaign_id, data in self._catalog_campaigns.items()
                    ]
                }
            }
        }

    async def fetch_campaigns(
        self, campaigns_chunk: list[tuple[str, JsonType]]
    ) -> dict[str, JsonType]:
        if self._catalog_campaigns:
            return {
                campaign_id: self._catalog_campaigns[campaign_id]
                for campaign_id, _ in campaigns_chunk
                if campaign_id in self._catalog_campaigns
            }
        return await super().fetch_campaigns(campaigns_chunk)
