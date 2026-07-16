from __future__ import annotations

from dataclasses import asdict
from typing import Any, TYPE_CHECKING

from yarl import URL

from core.constants import LANG_PATH
from tui.manager import TUIInventory, TUIManager

if TYPE_CHECKING:
    from models.inventory import DropsCampaign, TimedDrop
    from network.twitch import Twitch


class WebInventory(TUIInventory):
    def __init__(self, manager: WebManager) -> None:
        super().__init__(manager)
        self.campaigns: dict[str, DropsCampaign] = {}

    def clear(self) -> None:
        self.campaigns.clear()
        super().clear()

    async def add_campaign(self, campaign: DropsCampaign) -> None:
        self.campaigns[campaign.id] = campaign
        await super().add_campaign(campaign)


class WebManager(TUIManager):
    def __init__(self, twitch: Twitch) -> None:
        super().__init__(twitch)
        self.inv = WebInventory(self)
        self._selected_channel_id: str | None = None

    def start(self) -> None:
        self._app_ready.set()

    async def wait_until_ready(self) -> None:
        return None

    def stop(self) -> None:
        self.progress.stop_timer()

    def selected_channel_id(self) -> str | None:
        return self._selected_channel_id

    def select_channel(self, channel_id: str) -> bool:
        if channel_id not in self.channels._channel_map:
            return False
        self._selected_channel_id = channel_id
        self._switch_channel()
        return True

    def reload(self) -> None:
        self._reload()

    def invalidate_auth(self) -> None:
        self._invalidate_auth()

    def update_settings(self, payload: dict[str, Any]) -> None:
        if "priority" in payload or "exclude" in payload:
            priority = payload.get("priority", self.state.priority)
            exclude = payload.get("exclude", self.state.exclude)
            self._save_settings(",".join(priority), ",".join(exclude))
        if "priority_mode" in payload:
            self._set_priority_mode(payload["priority_mode"])
        if "farm_unlinked" in payload:
            self._set_farm_unlinked(payload["farm_unlinked"])
        if "enable_badges_emotes" in payload:
            self._set_badges_emotes(payload["enable_badges_emotes"])
        settings = self._twitch.settings
        restart_keys = {"proxy", "language", "connection_quality"}
        for key in restart_keys | {"available_drops_check"}:
            if key in payload:
                setattr(settings, key, URL(payload[key]) if key == "proxy" else payload[key])
        if restart_keys & payload.keys() or "available_drops_check" in payload:
            settings.save()
            self._update_settings_text()
            self.print("Server settings saved. Restart the miner to apply connection changes.")

    @staticmethod
    def _drop(drop: TimedDrop) -> dict[str, Any]:
        return {
            "id": drop.id,
            "name": drop.name,
            "progress": drop.progress,
            "current_minutes": drop.current_minutes,
            "required_minutes": drop.required_minutes,
            "claimed": drop.is_claimed,
            "claimable": drop.can_claim,
            "starts": drop.starts_at.isoformat(),
            "ends": drop.ends_at.isoformat(),
            "benefits": [
                {"id": benefit.id, "name": benefit.name, "image_url": str(benefit.image_url)}
                for benefit in drop.benefits
            ],
        }

    def snapshot(self) -> dict[str, Any]:
        campaigns = []
        for campaign in self.inv.campaigns.values():
            summary = self.state.campaigns.get(campaign.id)
            campaigns.append(
                {
                    **(asdict(summary) if summary is not None else {}),
                    "category_image_url": str(campaign.image_url),
                    "link_url": campaign.link_url,
                    "drops": [self._drop(drop) for drop in campaign.drops],
                }
            )

        current = asdict(self.state.current_drop)
        if self.progress._drop is not None:
            current["category_image_url"] = str(self.progress._drop.campaign.image_url)
            current["benefits"] = [
                {"name": benefit.name, "image_url": str(benefit.image_url)}
                for benefit in self.progress._drop.benefits
            ]

        return {
            "status": self.state.status,
            "icon_state": self.state.icon_state,
            "login": asdict(self.state.login),
            "current_drop": current,
            "channels": [asdict(channel) for channel in self.state.channels.values()],
            "campaigns": campaigns,
            "websockets": [asdict(socket) for socket in self.state.websockets.values()],
            "settings": {
                "priority": self.state.priority,
                "exclude": self.state.exclude,
                "available_games": self.state.available_games,
                "priority_mode": self.state.priority_mode,
                "priority_modes": list(self.PRIORITY_MODE_LABELS.values()),
                "farm_unlinked": self.state.farm_unlinked,
                "enable_badges_emotes": self.state.enable_badges_emotes,
                "available_drops_check": bool(self._twitch.settings.available_drops_check),
                "proxy": str(self._twitch.settings.proxy),
                "language": self._twitch.settings.language,
                "languages": ["English", *(path.stem for path in sorted(LANG_PATH.glob("*.json")))],
                "connection_quality": int(self._twitch.settings.connection_quality),
            },
            "selected_channel_id": self._selected_channel_id,
            "logs": self.state.logs[-200:],
        }
