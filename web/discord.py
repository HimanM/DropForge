from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

import aiohttp

from web.auth import AuthStore

if TYPE_CHECKING:
    from models.channel import Channel
    from models.inventory import DropsCampaign, TimedDrop
    from web.manager import WebManager


logger = logging.getLogger("TwitchDrops")
_ORANGE = 0xE9773D
_GREEN = 0x2DBA83
_RED = 0xD9534F
_WEBHOOK_PATH = re.compile(r"^/api(?:/v\d+)?/webhooks/(\d+)/([A-Za-z0-9._-]+)$")
_DEFAULTS = {
    "discord_url": "",
    "discord_enabled": "0",
    "discord_claimed": "1",
    "discord_new_drops": "1",
    "discord_status": "1",
    "discord_operational": "0",
    "discord_baseline": "0",
}


def _trim(value: Any, limit: int = 1024) -> str:
    text = str(value or "-").strip()
    return text if len(text) <= limit else f"{text[:limit - 1]}…"


def _image(value: Any) -> str | None:
    url = str(value or "")
    return url if urlsplit(url).scheme == "https" else None


def validate_webhook_url(value: str) -> str:
    if len(value) > 2048:
        raise ValueError("Discord webhook URL is too long.")
    parts = urlsplit(value.strip())
    if (
        parts.scheme != "https"
        or parts.hostname not in {"discord.com", "ptb.discord.com", "canary.discord.com"}
        or parts.port is not None
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
        or _WEBHOOK_PATH.fullmatch(parts.path) is None
    ):
        raise ValueError("Enter an official Discord webhook URL.")
    return urlunsplit(("https", parts.hostname, parts.path, "", ""))


class DiscordNotifier:
    def __init__(self, store: AuthStore) -> None:
        self.store = store
        self._tasks: set[asyncio.Task[None]] = set()
        self._watching_id: int | None = None
        self._has_watched = False
        self._idle_reason: tuple[str, tuple[str, ...]] | None = None

    def _settings(self) -> dict[str, str]:
        return self.store.get_settings(_DEFAULTS)

    def snapshot(self) -> dict[str, Any]:
        settings = self._settings()
        match = _WEBHOOK_PATH.fullmatch(urlsplit(settings["discord_url"]).path)
        return {
            "enabled": settings["discord_enabled"] == "1",
            "configured": bool(settings["discord_url"]),
            "webhook_label": f"Webhook …{match.group(1)[-6:]}" if match else "Not configured",
            "notify_claimed": settings["discord_claimed"] == "1",
            "notify_new_drops": settings["discord_new_drops"] == "1",
            "notify_status": settings["discord_status"] == "1",
            "notify_operational": settings["discord_operational"] == "1",
        }

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        keys = {
            "enabled": "discord_enabled",
            "notify_claimed": "discord_claimed",
            "notify_new_drops": "discord_new_drops",
            "notify_status": "discord_status",
            "notify_operational": "discord_operational",
        }
        updates: dict[str, str | None] = {}
        if "webhook_url" in payload:
            value = payload["webhook_url"]
            if not isinstance(value, str):
                raise ValueError("Discord webhook URL must be text.")
            updates["discord_url"] = validate_webhook_url(value) if value.strip() else None
            if not value.strip():
                updates["discord_enabled"] = "0"
        for public, stored in keys.items():
            if public in payload:
                if not isinstance(payload[public], bool):
                    raise ValueError(f"{public} must be true or false.")
                updates[stored] = "1" if payload[public] else "0"
        if not updates:
            raise ValueError("No supported notification settings were provided.")
        current = self._settings()
        next_url = updates.get("discord_url", current["discord_url"])
        next_enabled = updates.get("discord_enabled", current["discord_enabled"])
        if next_enabled == "1" and not next_url:
            raise ValueError("Add a Discord webhook URL before enabling notifications.")
        self.store.update_settings(updates)
        return self.snapshot()

    async def test(self) -> None:
        url = self._settings()["discord_url"]
        if not url:
            raise ValueError("Add and save a Discord webhook URL first.")
        await self._post(url, self._payload([
            self._embed(
                "DropForge notifications are ready",
                "This test confirms that the server can deliver formatted Discord messages.",
                _GREEN,
                fields=[
                    ("Priority filter", "Only categories in your priority list"),
                    ("Media", "Category art and reward images are included when Twitch provides them"),
                ],
            )
        ]))

    async def close(self) -> None:
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    def finish_inventory(self) -> None:
        if self._settings()["discord_baseline"] != "1":
            self.store.update_settings({"discord_baseline": "1"})

    def observe_campaign(self, campaign: DropsCampaign, priority: list[str]) -> None:
        baseline = self._settings()["discord_baseline"] == "1"
        new_drops = [
            drop for drop in campaign.drops
            if self.store.claim_notification_event(f"discord:seen:{drop.id}")
        ]
        if baseline and new_drops and campaign.game.name in priority and self._enabled("new_drops"):
            self._schedule(self._new_drops_payload(campaign, new_drops))

    def drop_updated(self, drop: TimedDrop, priority: list[str]) -> None:
        campaign = drop.campaign
        if drop.is_claimed and self.store.claim_notification_event(f"discord:claimed:{drop.id}"):
            if campaign.game.name in priority and self._enabled("claimed"):
                self._schedule(self._claimed_payload(drop))
        if campaign.finished and self.store.claim_notification_event(
            f"discord:complete:{campaign.id}"
        ):
            if campaign.game.name in priority and self._enabled("status"):
                self._schedule(self._campaign_complete_payload(campaign))

    def idle(self, manager: WebManager) -> None:
        priority = list(manager._twitch.settings.priority)
        if not priority:
            return
        next_hour = datetime.now(timezone.utc) + timedelta(hours=1)
        campaigns = [
            campaign for campaign in manager.inv.campaigns.values()
            if campaign.game.name in priority and campaign.can_earn_within(next_hour)
        ]
        categories = tuple(name for name in priority if any(c.game.name == name for c in campaigns))
        if not categories:
            categories = tuple(priority)
            reason = "No earnable priority drops"
            detail = "No active or upcoming priority campaign can currently make progress."
        else:
            channels = [
                channel for channel in manager._twitch.channels.values()
                if channel.game is not None and channel.game.name in categories
            ]
            online = [channel for channel in channels if channel.online]
            if not online:
                reason = "No live priority channels"
                detail = "No tracked live channel is streaming an earnable priority category."
            elif not any(channel.drops_enabled for channel in online):
                reason = "Drops disabled on live channels"
                detail = "Matching channels are live, but Twitch reports Drops as disabled."
            else:
                reason = "No eligible priority channel"
                detail = "Live channels exist, but none currently satisfy the campaign requirements."
        state = (reason, categories)
        self._idle_reason = state
        self._watching_id = None
        key = f"discord:idle:{reason}:{'|'.join(categories)}"
        if self._enabled("status") and self.store.claim_notification_event(key, cooldown=30 * 60):
            image = _image(campaigns[0].image_url) if campaigns else None
            self._schedule(self._status_payload(reason, detail, categories, _RED, image=image))

    def watching(self, manager: WebManager, channel: Channel) -> None:
        game = channel.game.name if channel.game is not None else ""
        if game not in manager._twitch.settings.priority:
            return
        if self._watching_id == channel.id and self._idle_reason is None:
            return
        resumed = self._idle_reason is not None
        first = not self._has_watched
        self._watching_id = channel.id
        self._has_watched = True
        self._idle_reason = None
        if not self._enabled("status") or not (first or resumed):
            return
        campaign = next(
            (item for item in manager.inv.campaigns.values() if item.game.name == game), None
        )
        title = "Mining resumed" if resumed else "Mining started"
        detail = f"Watching **{_trim(channel.name, 80)}** for priority Drops."
        self._schedule(self._status_payload(
            title, detail, (game,), _GREEN,
            image=_image(campaign.image_url) if campaign else None,
        ))

    def miner_stopped(self, manager: WebManager) -> None:
        drop = manager.progress._drop
        game = drop.campaign.game.name if drop is not None else ""
        if game not in manager._twitch.settings.priority or not self._enabled("status"):
            return
        self._watching_id = None
        self._schedule(self._status_payload(
            "Mining stopped",
            "The miner was stopped from the DropForge web interface.",
            (game,),
            _RED,
            image=_image(drop.campaign.image_url),
        ))

    def operational(self, title: str, detail: str) -> None:
        if self._enabled("operational"):
            self._schedule(self._payload([self._embed(title, detail, _RED)]))

    def _enabled(self, event: str) -> bool:
        settings = self._settings()
        return bool(settings["discord_url"]) and settings["discord_enabled"] == "1" and settings[
            f"discord_{event}"
        ] == "1"

    def _schedule(self, payload: dict[str, Any]) -> None:
        if len(self._tasks) >= 10:
            logger.warning("Discord notification queue is full; dropping an event.")
            return
        url = self._settings()["discord_url"]
        task = asyncio.create_task(self._post(url, payload))
        self._tasks.add(task)
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.warning("Discord notification failed: %s", error)

    async def _post(self, url: str, payload: dict[str, Any]) -> None:
        timeout = aiohttp.ClientTimeout(total=12)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for attempt in range(2):
                async with session.post(f"{url}?wait=true", json=payload) as response:
                    if response.status == 429 and attempt == 0:
                        data = await response.json(content_type=None)
                        await asyncio.sleep(min(float(data.get("retry_after", 1)), 10))
                        continue
                    if 200 <= response.status < 300:
                        return
                    detail = _trim(await response.text(), 200)
                    raise RuntimeError(f"Discord returned HTTP {response.status}: {detail}")
        raise RuntimeError("Discord rate limit retry failed.")

    @staticmethod
    def _payload(embeds: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "username": "DropForge",
            "allowed_mentions": {"parse": []},
            "embeds": embeds[:10],
        }

    @staticmethod
    def _embed(
        title: str,
        description: str,
        color: int,
        *,
        fields: list[tuple[str, str]] | None = None,
        image: str | None = None,
        thumbnail: str | None = None,
        url: str | None = None,
    ) -> dict[str, Any]:
        embed: dict[str, Any] = {
            "title": _trim(title, 256),
            "description": _trim(description, 4096),
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "DropForge | Priority notifications"},
        }
        if fields:
            embed["fields"] = [
                {"name": _trim(name, 256), "value": _trim(value), "inline": True}
                for name, value in fields[:25]
            ]
        if image:
            embed["image"] = {"url": image}
        if thumbnail:
            embed["thumbnail"] = {"url": thumbnail}
        if url and _image(url):
            embed["url"] = url
        return embed

    def _new_drops_payload(
        self, campaign: DropsCampaign, drops: list[TimedDrop]
    ) -> dict[str, Any]:
        overflow = max(0, len(drops) - 9)
        fields = [
            ("Category", campaign.game.name),
            ("Campaign", campaign.name),
            ("New Drops", str(len(drops))),
            ("Ends", campaign.ends_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")),
        ]
        if overflow:
            fields.append(("More", f"{overflow} additional Drops are available in Twitch."))
        embeds = [self._embed(
            "New priority Drops detected",
            "DropForge found new rewards for a category in your priority list.",
            _ORANGE,
            fields=fields,
            image=_image(campaign.image_url),
            url=str(campaign.link_url),
        )]
        embeds.extend(self._drop_embed(drop) for drop in drops[:9])
        return self._payload(embeds)

    def _drop_embed(self, drop: TimedDrop) -> dict[str, Any]:
        reward = ", ".join(benefit.name for benefit in drop.benefits) or drop.name
        thumbnail = next((_image(benefit.image_url) for benefit in drop.benefits if _image(benefit.image_url)), None)
        return self._embed(
            drop.name or "Twitch Drop",
            reward,
            _ORANGE,
            fields=[
                ("Watch time", f"{drop.required_minutes} minutes"),
                ("Available until", drop.ends_at.astimezone().strftime("%Y-%m-%d %H:%M %Z")),
            ],
            thumbnail=thumbnail,
        )

    def _claimed_payload(self, drop: TimedDrop) -> dict[str, Any]:
        campaign = drop.campaign
        reward = ", ".join(benefit.name for benefit in drop.benefits) or drop.name
        thumbnail = next((_image(benefit.image_url) for benefit in drop.benefits if _image(benefit.image_url)), None)
        return self._payload([self._embed(
            "Drop claimed",
            reward,
            _GREEN,
            fields=[
                ("Category", campaign.game.name),
                ("Campaign", campaign.name),
                ("Campaign progress", f"{campaign.claimed_drops}/{campaign.total_drops} Drops claimed"),
            ],
            image=_image(campaign.image_url),
            thumbnail=thumbnail,
            url=str(campaign.link_url),
        )])

    def _campaign_complete_payload(self, campaign: DropsCampaign) -> dict[str, Any]:
        return self._payload([self._embed(
            "Priority campaign complete",
            "Every earnable Drop in this campaign has been claimed.",
            _GREEN,
            fields=[("Category", campaign.game.name), ("Campaign", campaign.name)],
            image=_image(campaign.image_url),
            url=str(campaign.link_url),
        )])

    def _status_payload(
        self,
        title: str,
        detail: str,
        categories: tuple[str, ...],
        color: int,
        *,
        image: str | None = None,
    ) -> dict[str, Any]:
        return self._payload([self._embed(
            title,
            detail,
            color,
            fields=[("Priority categories", ", ".join(categories))],
            image=image,
        )])
