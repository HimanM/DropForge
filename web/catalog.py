from __future__ import annotations

import asyncio
import json
import logging
from time import time
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
CATALOG_DETAIL_TTL = 24 * 60 * 60
CATALOG_REFRESH_BATCH = 10


class WebTwitch(Twitch):
    """Web-only Twitch client with public campaign discovery fallback."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._catalog_campaigns: dict[str, JsonType] = {}

    def _merge_data(self, primary_data: JsonType, secondary_data: JsonType) -> JsonType:
        if not self._catalog_campaigns:
            return super()._merge_data(primary_data, secondary_data)
        merged = dict(secondary_data)
        for key, value in primary_data.items():
            if key == "allow" and isinstance(merged.get(key), dict):
                continue
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._merge_data(value, merged[key])
            else:
                merged[key] = value
        return merged

    @staticmethod
    def _asset_url(value: str) -> str:
        return str(CATALOG_ORIGIN.join(URL(value))) if value else ""

    def _reuse_cached_detail(self, item: JsonType, cached_item: JsonType) -> bool:
        game = item.get("game") or {}
        return (
            cached_item.get("updated_at") == str(item.get("updated_at") or "")
            and not (
                str(item.get("status") or "").lower() == "active"
                and item.get("allow_is_enabled") is True
                and isinstance(game, dict)
                and (game.get("display_name") or game.get("name"))
                in getattr(self.settings, "priority", ())
            )
        )

    @staticmethod
    def _cache_expired(cached_item: JsonType, now: float) -> bool:
        fetched_at = cached_item.get("fetched_at")
        return not isinstance(fetched_at, (int, float)) or fetched_at <= (
            now - CATALOG_DETAIL_TTL
        )

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
            proxy = getattr(self.settings, "proxy", None) or None
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(
                timeout=timeout, cookie_jar=aiohttp.DummyCookieJar()
            ) as session:
                async def fetch_json(url: URL) -> JsonType:
                    async with session.get(
                        url,
                        headers={"Accept": "application/json"},
                        proxy=proxy,
                        allow_redirects=False,
                    ) as response:
                        body = await response.read()
                    if response.status != 200:
                        raise RuntimeError(f"campaign catalogue HTTP {response.status}")
                    if len(body) > 2_000_000:
                        raise RuntimeError("campaign catalogue response is too large")
                    payload = json.loads(body)
                    if not isinstance(payload, dict):
                        raise RuntimeError("campaign catalogue returned invalid JSON")
                    return payload

                items: list[JsonType] = []
                list_url = CATALOG_ORIGIN / "api/v1/twitch/campaigns/"
                for status in ("active", "upcoming"):
                    page = 1
                    while True:
                        payload = await fetch_json(
                            list_url.with_query(
                                status=status, page=page, page_size=10
                            )
                        )
                        page_items = payload.get("items")
                        total = payload.get("total")
                        if (
                            not isinstance(page_items, list)
                            or len(page_items) > 10
                            or not isinstance(total, int)
                            or not 0 <= total <= 2_000
                        ):
                            raise RuntimeError("campaign catalogue returned an invalid list")
                        items.extend(
                            item for item in page_items if isinstance(item, dict)
                        )
                        if page * 10 >= total:
                            break
                        if not page_items:
                            raise RuntimeError("campaign catalogue pagination stopped early")
                        page += 1

                current: dict[str, JsonType] = {}
                changed: list[tuple[str, str]] = []
                refreshed_cached = 0
                now = time()
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
                    if isinstance(cached_item, dict) and isinstance(
                        cached_item.get("detail"), dict
                    ):
                        current[campaign_id] = cached_item
                        if self._reuse_cached_detail(item, cached_item):
                            if (
                                refreshed_cached >= CATALOG_REFRESH_BATCH
                                or not self._cache_expired(cached_item, now)
                            ):
                                continue
                            refreshed_cached += 1
                    changed.append((campaign_id, updated_at))

                async def fetch_detail(
                    campaign_id: str, updated_at: str
                ) -> tuple[str, JsonType]:
                    url = CATALOG_ORIGIN / f"api/v1/twitch/campaigns/{campaign_id}/"
                    detail = await fetch_json(url)
                    if detail.get("twitch_id") != campaign_id:
                        raise RuntimeError(
                            "campaign catalogue returned invalid campaign details"
                        )
                    return campaign_id, {
                        "updated_at": updated_at,
                        "fetched_at": int(time()),
                        "detail": detail,
                    }

                for entries in chunk(changed, 10):
                    results = await asyncio.gather(
                        *(fetch_detail(*entry) for entry in entries),
                        return_exceptions=True,
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

        response: JsonType = {"data": {"currentUser": {"dropCampaigns": []}}}
        original_error: GQLException | None = None
        if not self._catalog_campaigns:
            try:
                response = await super().gql_request(ops)
                campaigns = ((response.get("data") or {}).get("currentUser") or {}).get(
                    "dropCampaigns"
                )
                if campaigns:
                    return response
            except GQLException as exc:
                if (
                    "IntegrityCheckFailed" not in str(exc)
                    and "failed integrity check" not in str(exc)
                ):
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
