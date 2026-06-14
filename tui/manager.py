from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING

from yarl import URL

from core.constants import PriorityMode, State
from core.exceptions import ExitRequest
from core.translate import _
from tui.app import TwitchDropsTUI
from tui.state import (
    CampaignSnapshot,
    ChannelSnapshot,
    DropSnapshot,
    LoginSnapshot,
    TUIState,
    WebsocketSnapshot,
)

if TYPE_CHECKING:
    from collections import abc

    from core.utils import Game
    from models.channel import Channel
    from models.inventory import DropsCampaign, TimedDrop
    from network.twitch import Twitch


logger = logging.getLogger("TwitchDrops")


@dataclass(slots=True)
class LoginData:
    username: str
    password: str
    token: str


def _format_duration(minutes: int, seconds: int = 0) -> str:
    total = max(0, minutes * 60 + seconds)
    hours, remainder = divmod(total, 3600)
    mins, secs = divmod(remainder, 60)
    return f"{hours:02}:{mins:02}:{secs:02}"


class TUIStatus:
    def __init__(self, manager: TUIManager) -> None:
        self._manager = manager

    def update(self, status: str) -> None:
        self._manager.state.status = status
        self._manager.refresh_status()


class TUIWebsocketStatus:
    def __init__(self, manager: TUIManager) -> None:
        self._manager = manager

    def update(self, idx: int, status: str | None = None, topics: int | None = None) -> None:
        snapshot = self._manager.state.websockets.get(idx, WebsocketSnapshot(idx))
        if status is not None:
            snapshot.status = status
        if topics is not None:
            snapshot.topics = topics
        self._manager.state.websockets[idx] = snapshot
        self._manager.refresh_status()

    def remove(self, idx: int) -> None:
        self._manager.state.websockets.pop(idx, None)
        self._manager.refresh_status()


class TUILogin:
    def __init__(self, manager: TUIManager) -> None:
        self._manager = manager
        self._confirm = asyncio.Event()

    def clear(self, login: bool = False, password: bool = False, token: bool = False) -> None:
        return None

    def update(self, status: str, user_id: int | None) -> None:
        self._manager.state.login.status = status
        self._manager.state.login.user_id = str(user_id) if user_id is not None else "-"
        if user_id is not None:
            self._manager.state.login.activation_url = ""
            self._manager.state.login.user_code = ""
        self._manager.refresh_login()

    async def ask_login(self) -> LoginData:
        self._manager.print(
            "Username/password login is not used by the TUI. Device login will be requested."
        )
        await asyncio.sleep(0)
        return LoginData("", "", "")

    async def ask_enter_code(self, page_url: URL, user_code: str) -> None:
        url = str(page_url)
        self._confirm.clear()
        self._manager.state.login = LoginSnapshot(
            status=_("gui", "login", "required"),
            user_id="-",
            activation_url=url,
            user_code=user_code,
        )
        self._manager.print("Twitch login required.")
        self._manager.print(f"Open this URL: {url}")
        self._manager.print(f"Enter this code: {user_code}")
        self._manager.refresh_login()
        await asyncio.sleep(0)

    def confirm(self) -> None:
        self._confirm.set()


class TUIProgress:
    ALMOST_DONE_SECONDS = 10

    def __init__(self, manager: TUIManager) -> None:
        self._manager = manager
        self._drop: TimedDrop | None = None
        self._seconds = 0
        self._timer_task: asyncio.Task[None] | None = None

    def _snapshot(self) -> DropSnapshot:
        drop = self._drop
        if drop is None:
            return DropSnapshot()
        campaign = drop.campaign
        return DropSnapshot(
            campaign=campaign.name,
            game=campaign.game.name,
            rewards=drop.rewards_text(),
            drop_progress=drop.progress,
            campaign_progress=campaign.progress,
            remaining=_format_duration(drop.remaining_minutes, self._seconds % 60),
        )

    def _publish(self) -> None:
        self._manager.state.set_drop(self._snapshot())
        self._manager.refresh_progress()

    async def _timer_loop(self) -> None:
        self._seconds = 60
        self._publish()
        while self._seconds > 0:
            await asyncio.sleep(1)
            self._seconds -= 1
            self._publish()
        self._timer_task = None

    def start_timer(self) -> None:
        if self._timer_task is None:
            if self._drop is None or self._drop.remaining_minutes <= 0:
                self._seconds = 60
                self._publish()
            else:
                self._timer_task = asyncio.create_task(self._timer_loop())

    def stop_timer(self) -> None:
        if self._timer_task is not None:
            self._timer_task.cancel()
            self._timer_task = None

    def minute_almost_done(self) -> bool:
        return self._timer_task is None or self._seconds <= self.ALMOST_DONE_SECONDS

    def display(self, drop: TimedDrop | None, *, countdown: bool = True, subone: bool = False) -> None:
        self.stop_timer()
        self._drop = drop
        if drop is None:
            self._seconds = 0
            self._publish()
            return
        if countdown:
            self.start_timer()
        elif subone:
            self._seconds = 0
            self._publish()
        else:
            self._seconds = 60
            self._publish()


class TUIChannels:
    def __init__(self, manager: TUIManager) -> None:
        self._manager = manager
        self._channel_map: dict[str, Channel] = {}

    def _snapshot(self, channel: Channel, *, watching: bool = False) -> ChannelSnapshot:
        if channel.online:
            status = _("gui", "channels", "online")
        elif channel.pending_online:
            status = _("gui", "channels", "pending")
        else:
            status = _("gui", "channels", "offline")
        return ChannelSnapshot(
            iid=channel.iid,
            name=channel.name,
            status=status,
            game=str(channel.game or ""),
            viewers=str(channel.viewers or ""),
            drops=channel.drops_enabled,
            acl_based=channel.acl_based,
            watching=watching,
        )

    def clear(self) -> None:
        self._channel_map.clear()
        self._manager.state.channels.clear()
        self._manager.refresh_channels()

    def display(self, channel: Channel, *, add: bool = False) -> None:
        iid = channel.iid
        if not add and iid not in self._channel_map:
            return
        watching = self._manager.state.channels.get(iid, self._snapshot(channel)).watching
        self._channel_map[iid] = channel
        self._manager.state.channels[iid] = self._snapshot(channel, watching=watching)
        self._manager.refresh_channels()

    def remove(self, channel: Channel) -> None:
        self._channel_map.pop(channel.iid, None)
        self._manager.state.channels.pop(channel.iid, None)
        self._manager.refresh_channels()

    def set_watching(self, channel: Channel) -> None:
        for iid, snapshot in list(self._manager.state.channels.items()):
            self._manager.state.channels[iid] = ChannelSnapshot(
                iid=snapshot.iid,
                name=snapshot.name,
                status=snapshot.status,
                game=snapshot.game,
                viewers=snapshot.viewers,
                drops=snapshot.drops,
                acl_based=snapshot.acl_based,
                watching=iid == channel.iid,
            )
        if channel.iid not in self._manager.state.channels:
            self._manager.state.channels[channel.iid] = self._snapshot(channel, watching=True)
        self._manager.refresh_channels()

    def clear_watching(self) -> None:
        for iid, snapshot in list(self._manager.state.channels.items()):
            self._manager.state.channels[iid] = ChannelSnapshot(
                iid=snapshot.iid,
                name=snapshot.name,
                status=snapshot.status,
                game=snapshot.game,
                viewers=snapshot.viewers,
                drops=snapshot.drops,
                acl_based=snapshot.acl_based,
                watching=False,
            )
        self._manager.refresh_channels()

    def get_selection(self) -> Channel | None:
        selected = self._manager.selected_channel_id()
        if selected is None:
            return None
        return self._channel_map.get(selected)


class TUIInventory:
    def __init__(self, manager: TUIManager) -> None:
        self._manager = manager

    def _campaign_status(self, campaign: DropsCampaign) -> str:
        if campaign.active:
            return _("gui", "inventory", "status", "active")
        if campaign.upcoming:
            return _("gui", "inventory", "status", "upcoming")
        return _("gui", "inventory", "status", "expired")

    def _snapshot(self, campaign: DropsCampaign) -> CampaignSnapshot:
        allowed = campaign.allowed_channels
        if allowed:
            allowed_channels = ", ".join(ch.name for ch in allowed[:5])
            if len(allowed) > 5:
                allowed_channels += f", +{len(allowed) - 5}"
        else:
            allowed_channels = _("gui", "inventory", "all_channels")
        drops = tuple(
            f"{drop.rewards_text()} - {drop.progress:.1%} ({drop.current_minutes}/{drop.required_minutes} min)"
            for drop in campaign.drops
        )
        settings = self._manager._twitch.settings
        priority_only = settings.priority_mode is PriorityMode.PRIORITY_ONLY
        game_name = campaign.game.name
        return CampaignSnapshot(
            id=campaign.id,
            name=campaign.name,
            game=game_name,
            status=self._campaign_status(campaign),
            linked=campaign.eligible,
            active=campaign.active,
            upcoming=campaign.upcoming,
            expired=campaign.expired,
            excluded=game_name in settings.exclude
            or priority_only and game_name not in settings.priority,
            finished=campaign.finished,
            required_minutes=campaign.required_minutes,
            progress=campaign.progress,
            drops=drops,
            starts=str(campaign.starts_at.astimezone().replace(microsecond=0, tzinfo=None)),
            ends=str(campaign.ends_at.astimezone().replace(microsecond=0, tzinfo=None)),
            allowed_channels=allowed_channels,
        )

    def clear(self) -> None:
        self._manager.state.campaigns.clear()
        self._manager.refresh_campaigns()

    async def add_campaign(self, campaign: DropsCampaign) -> None:
        self._manager.state.campaigns[campaign.id] = self._snapshot(campaign)
        self._manager.refresh_campaigns()

    def update_drop(self, drop: TimedDrop) -> None:
        campaign = drop.campaign
        if campaign.id in self._manager.state.campaigns:
            self._manager.state.campaigns[campaign.id] = self._snapshot(campaign)
            self._manager.refresh_campaigns()
        if self._manager.progress._drop is drop:
            self._manager.progress._publish()


class TUITray:
    def __init__(self, manager: TUIManager) -> None:
        self._manager = manager

    def change_icon(self, state: str) -> None:
        self._manager.state.icon_state = state
        self._manager.refresh_status()

    def notify(self, text: str, title: str) -> asyncio.Task[None] | None:
        self._manager.print(f"{title}: {text.replace(chr(10), ' ')}")
        return None

    def update_title(self, drop: TimedDrop | None) -> None:
        return None

    def stop(self) -> None:
        return None


class TUIManager:
    READY_TIMEOUT = 2.0
    PRIORITY_MODE_LABELS = {
        PriorityMode.PRIORITY_ONLY: "Priority list only",
        PriorityMode.ENDING_SOONEST: "Ending soonest",
        PriorityMode.LOW_AVBL_FIRST: "Low availability first",
    }

    def __init__(self, twitch: Twitch) -> None:
        self._twitch = twitch
        self.state = TUIState()
        self._close_requested = asyncio.Event()
        self._app_ready = asyncio.Event()
        self._app: TwitchDropsTUI | None = None
        self._app_task: asyncio.Task[Any] | None = None

        self.status = TUIStatus(self)
        self.websockets = TUIWebsocketStatus(self)
        self.login = TUILogin(self)
        self.progress = TUIProgress(self)
        self.channels = TUIChannels(self)
        self.inv = TUIInventory(self)
        self.tray = TUITray(self)
        self._games: set[Game] = set()
        self._update_settings_text()

    @property
    def close_requested(self) -> bool:
        return self._close_requested.is_set()

    def _update_settings_text(self) -> None:
        settings = self._twitch.settings
        priority_mode = getattr(settings, "priority_mode", PriorityMode.PRIORITY_ONLY)
        self.state.priority = list(getattr(settings, "priority", []))
        self.state.exclude = sorted(getattr(settings, "exclude", []))
        self.state.priority_mode = self.PRIORITY_MODE_LABELS.get(
            priority_mode,
            self.PRIORITY_MODE_LABELS[PriorityMode.PRIORITY_ONLY],
        )
        self.state.farm_unlinked = bool(getattr(settings, "farm_unlinked", False))
        self.state.available_games = sorted(game.name for game in self._games)
        self.state.settings_text = (
            f"Mode: {self.state.priority_mode} | "
            f"Priority: {len(self.state.priority)} | "
            f"Exclude: {len(self.state.exclude)} | "
            f"Farm unlinked: {self.state.farm_unlinked} | "
            f"Games: {len(self.state.available_games)}"
        )
        self.refresh_settings()

    def start(self) -> None:
        if self._app_task is not None and not self._app_task.done():
            return
        self._app_ready.clear()
        self._app = TwitchDropsTUI(
            self.state,
            on_close=self.close,
            on_reload=self._reload,
            login_confirm=self.login.confirm,
            on_switch=self._switch_channel,
            on_save_settings=self._save_settings,
            on_add_priority_game=self._add_priority_game,
            on_add_exclude_game=self._add_exclude_game,
            on_remove_priority_game=self._remove_priority_game,
            on_remove_exclude_game=self._remove_exclude_game,
            on_move_priority_game=self._move_priority_game,
            on_set_priority_mode=self._set_priority_mode,
            on_set_farm_unlinked=self._set_farm_unlinked,
            on_ready=self._mark_app_ready,
        )
        self._app_task = asyncio.create_task(self._app.run_async())

    def _mark_app_ready(self) -> None:
        logger.info("Terminal UI ready.")
        self._app_ready.set()

    async def wait_until_ready(self) -> None:
        if self._app is None or self._app_ready.is_set():
            return
        try:
            await asyncio.wait_for(self._app_ready.wait(), timeout=self.READY_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("Terminal UI did not report ready before startup timeout.")
            if self._app is not None and self._app.is_running:
                self._app.exit()
            self._app_ready.set()

    def stop(self) -> None:
        self.progress.stop_timer()
        if self._app is not None and self._app.is_running:
            self._app.exit()

    def close(self, *args: Any) -> int:
        self._close_requested.set()
        self._twitch.close()
        if self._app is not None and self._app.is_running:
            self._app.exit()
        return 0

    def close_window(self) -> None:
        self.stop()

    async def wait_until_closed(self) -> None:
        await self._close_requested.wait()

    async def coro_unless_closed(self, coro: abc.Awaitable[Any]) -> Any:
        tasks = [asyncio.ensure_future(coro), asyncio.ensure_future(self._close_requested.wait())]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        if self.close_requested:
            raise ExitRequest()
        return await next(iter(done))

    def prevent_close(self) -> None:
        self._close_requested.clear()

    def save(self, *, force: bool = False) -> None:
        return None

    def grab_attention(self, *, sound: bool = True) -> None:
        if self._app is not None and self._app.is_running:
            self._app.notify("Input required")

    def set_games(self, games: set[Game]) -> None:
        self._games = games
        self._update_settings_text()

    def display_drop(
        self, drop: TimedDrop, *, countdown: bool = True, subone: bool = False
    ) -> None:
        self.progress.display(drop, countdown=countdown, subone=subone)
        self.tray.update_title(drop)

    def clear_drop(self) -> None:
        self.progress.display(None)
        self.tray.update_title(None)

    def print(self, message: str) -> None:
        stamp = datetime.now().strftime("%X")
        if "\n" in message:
            message = message.replace("\n", f"\n{stamp}: ")
        line = f"{stamp}: {message}"
        self.state.add_log(line)
        if self._app is not None:
            self._app.append_log_later(line)

    def selected_channel_id(self) -> str | None:
        if self._app is None or not self._app.is_running or not self._app.is_mounted:
            return None
        return self._app.selected_channel_id()

    def refresh_status(self) -> None:
        if self._app is not None:
            self._app.refresh_status_later()

    def refresh_login(self) -> None:
        if self._app is not None:
            self._app.refresh_login_later()

    def refresh_progress(self) -> None:
        if self._app is not None:
            self._app.refresh_progress_later()

    def refresh_channels(self) -> None:
        if self._app is not None:
            self._app.refresh_channels_later()

    def refresh_campaigns(self) -> None:
        if self._app is not None:
            self._app.refresh_campaigns_later()

    def refresh_settings(self) -> None:
        if self._app is not None:
            self._app.refresh_settings_later()

    def _reload(self) -> None:
        self._twitch.change_state(State.INVENTORY_FETCH)

    def _switch_channel(self) -> None:
        if self.selected_channel_id() is not None:
            self._twitch.change_state(State.CHANNEL_SWITCH)

    @staticmethod
    def _parse_game_list(raw: str) -> list[str]:
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _save_settings(self, priority_raw: str, exclude_raw: str) -> None:
        self._twitch.settings.priority = self._parse_game_list(priority_raw)
        self._twitch.settings.exclude = set(self._parse_game_list(exclude_raw))
        self._twitch.settings.save()
        self._update_settings_text()
        self.print("Settings lists saved. Reload inventory to apply changes.")

    def _save_settings_update(self, message: str) -> None:
        self._twitch.settings.save()
        self._update_settings_text()
        self.print(f"{message} Reload inventory to apply changes.")

    def _add_priority_game(self, game_name: str) -> None:
        if game_name and game_name not in self._twitch.settings.priority:
            self._twitch.settings.priority.append(game_name)
            self._save_settings_update(f"Added {game_name} to priority.")

    def _add_exclude_game(self, game_name: str) -> None:
        if game_name and game_name not in self._twitch.settings.exclude:
            self._twitch.settings.exclude.add(game_name)
            self._save_settings_update(f"Added {game_name} to exclude.")

    def _remove_priority_game(self, game_name: str) -> None:
        if game_name in self._twitch.settings.priority:
            self._twitch.settings.priority.remove(game_name)
            self._save_settings_update(f"Removed {game_name} from priority.")

    def _remove_exclude_game(self, game_name: str) -> None:
        if game_name in self._twitch.settings.exclude:
            self._twitch.settings.exclude.discard(game_name)
            self._save_settings_update(f"Removed {game_name} from exclude.")

    def _move_priority_game(self, game_name: str, offset: int) -> None:
        priority = self._twitch.settings.priority
        if game_name not in priority:
            return
        old_idx = priority.index(game_name)
        new_idx = max(0, min(len(priority) - 1, old_idx + offset))
        if old_idx == new_idx:
            return
        priority.pop(old_idx)
        priority.insert(new_idx, game_name)
        self._save_settings_update(f"Moved {game_name}.")

    def _set_priority_mode(self, mode_name: str) -> None:
        for mode, label in self.PRIORITY_MODE_LABELS.items():
            if label == mode_name:
                self._twitch.settings.priority_mode = mode
                if mode is not PriorityMode.PRIORITY_ONLY:
                    self._twitch.settings.farm_unlinked = False
                self._save_settings_update(f"Priority mode changed to {label}.")
                return

    def _set_farm_unlinked(self, enabled: bool) -> None:
        if self._twitch.settings.priority_mode is not PriorityMode.PRIORITY_ONLY:
            enabled = False
        self._twitch.settings.farm_unlinked = enabled
        self._save_settings_update(f"Farm unlinked drops set to {enabled}.")
