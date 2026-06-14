from __future__ import annotations

import asyncio
import shutil
import webbrowser
from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable

from prompt_toolkit.application import Application
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import has_completions
from prompt_toolkit.formatted_text import AnyFormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from core.constants import PriorityMode
from tui.manager import TUIManager
from tui.state import CampaignSnapshot

if TYPE_CHECKING:
    from core.utils import Game


class CommandCompleter(Completer):
    """Slash-command completer that works from the whole input line."""

    def __init__(
        self,
        commands: tuple[str, ...],
        argument_candidates: Callable[[str], list[str]] | None = None,
    ) -> None:
        self._commands = commands
        self._argument_candidates = argument_candidates or (lambda _command: [])

    def get_completions(self, document: Document, complete_event: CompleteEvent):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        argument_completion = self._argument_completion(text)
        if argument_completion is not None:
            fragment, candidates, needs_space = argument_completion
            for candidate in candidates:
                if candidate.lower().startswith(fragment.lower()):
                    yield Completion(
                        f" {candidate}" if needs_space else candidate,
                        start_position=-len(fragment),
                        display=candidate,
                    )
            return
        needle = text.lower()
        for command in self._commands:
            if command.lower().startswith(needle):
                yield Completion(command, start_position=-len(text), display=command)

    def _argument_completion(self, text: str) -> tuple[str, list[str], bool] | None:
        lowered = text.lower()
        for command in self._commands:
            candidates = self._argument_candidates(command)
            if not candidates:
                continue
            if lowered == command:
                return "", candidates, True
            prefix = f"{command} "
            if lowered.startswith(prefix):
                return text[len(prefix) :], candidates, False
        return None


class PortableCLIManager(TUIManager):
    """Full-screen prompt_toolkit frontend for portable terminal sessions."""

    CHANNEL_PAGE_SIZE = 10
    CAMPAIGN_PAGE_SIZE = 8
    COMMANDS = (
        "/dashboard",
        "/channels",
        "/channels next",
        "/channels prev",
        "/drops",
        "/drops next",
        "/drops prev",
        "/settings",
        "/logs",
        "/reload",
        "/open",
        "/copy",
        "/switch",
        "/priority add",
        "/priority remove",
        "/exclude add",
        "/exclude remove",
        "/mode",
        "/mode priority-only",
        "/mode ending-soonest",
        "/mode low-availability",
        "/filter not-linked",
        "/filter not-linked on",
        "/filter not-linked off",
        "/filter upcoming",
        "/filter upcoming on",
        "/filter upcoming off",
        "/filter expired",
        "/filter expired on",
        "/filter expired off",
        "/filter excluded",
        "/filter excluded on",
        "/filter excluded off",
        "/filter finished",
        "/filter finished on",
        "/filter finished off",
        "/farm-unlinked",
        "/farm-unlinked on",
        "/farm-unlinked off",
        "/help",
        "/quit",
    )

    def __init__(self, twitch: Any) -> None:
        self._pt_app: Application[None] | None = None
        super().__init__(twitch)
        self._view = "dashboard"
        self._channel_offset = 0
        self._campaign_offset = 0
        self._selected_channel: str | None = None
        self._input: TextArea | None = None
        self._pt_app_task: asyncio.Task[None] | None = None
        self._clock_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._pt_app_task is not None and not self._pt_app_task.done():
            return
        self._app_ready.clear()
        self._pt_app = self._make_app()
        self._pt_app_task = asyncio.create_task(self._pt_app.run_async())
        self._clock_task = asyncio.create_task(self._clock_loop())
        self._app_ready.set()

    async def wait_until_ready(self) -> None:
        await self._app_ready.wait()

    def stop(self) -> None:
        super().stop()
        if self._clock_task is not None:
            self._clock_task.cancel()
        if self._pt_app is not None and self._pt_app.future is not None and not self._pt_app.future.done():
            self._pt_app.exit()

    def close_window(self) -> None:
        self.stop()

    def close(self, *args: Any) -> int:
        result = super().close(*args)
        self.stop()
        return result

    def selected_channel_id(self) -> str | None:
        return self._selected_channel

    def refresh_status(self) -> None:
        self._invalidate()

    def refresh_login(self) -> None:
        self._invalidate()

    def refresh_progress(self) -> None:
        self._invalidate()

    def refresh_channels(self) -> None:
        self._invalidate()

    def refresh_campaigns(self) -> None:
        self._invalidate()

    def refresh_settings(self) -> None:
        self._invalidate()

    def _make_app(self) -> Application[None]:
        completer = CommandCompleter(self.COMMANDS, self._completion_candidates)
        self._input = TextArea(
            height=1,
            prompt=[("class:prompt", "> ")],
            completer=completer,
            complete_while_typing=True,
            multiline=False,
            accept_handler=self._accept_command,
        )
        body = HSplit(
            [
                Window(
                    FormattedTextControl(self._screen_fragments),
                    wrap_lines=False,
                    always_hide_cursor=True,
                ),
                Window(height=1, char="-", style="class:rule"),
                Frame(self._input, title="command"),
                ConditionalContainer(
                    CompletionsMenu(max_height=6, scroll_offset=1),
                    filter=has_completions,
                ),
            ]
        )
        bindings = KeyBindings()

        @bindings.add("c-c")
        @bindings.add("c-q")
        def _quit(event) -> None:
            self.close()

        return Application(
            layout=Layout(body, focused_element=self._input),
            key_bindings=bindings,
            full_screen=True,
            mouse_support=True,
            erase_when_done=False,
            style=Style.from_dict(
                {
                    "screen": "ansidefault bg:#101014",
                    "rule": "#5f5f5f",
                    "frame.border": "#00d7ff",
                    "frame.label": "bold #ffaf00",
                    "prompt": "bold #00d7ff",
                    "completion-menu.completion": "bg:#202028 #d7d7d7",
                    "completion-menu.completion.current": "bg:#005f87 #ffffff bold",
                    "completion-menu.meta.completion": "bg:#202028 #878787",
                    "completion-menu.meta.completion.current": "bg:#005f87 #ffffff",
                }
            ),
        )

    async def _clock_loop(self) -> None:
        while not self.close_requested:
            await asyncio.sleep(1)
            self._invalidate()

    def _invalidate(self) -> None:
        if self._pt_app is not None:
            self._pt_app.invalidate()

    def _accept_command(self, buffer) -> bool:
        raw = buffer.text.strip()
        buffer.text = ""
        self._handle_command(raw)
        self._invalidate()
        return True

    def _handle_command(self, raw: str) -> None:
        if not raw:
            return
        command, _, rest = raw.partition(" ")
        command = command.removeprefix("/").lower()
        rest = rest.strip()
        if command in {"q", "quit", "exit"}:
            self.close()
        elif command in {"dashboard", "home"}:
            self._view = "dashboard"
        elif command in {"channels", "ch"}:
            self._view = "channels"
            self._scroll_channels(rest)
        elif command in {"drops", "campaigns", "camps"}:
            self._view = "drops"
            self._scroll_campaigns(rest)
        elif command in {"settings", "config"}:
            self._view = "settings"
        elif command == "logs":
            self._view = "logs"
        elif command == "reload":
            self._reload()
        elif command == "open":
            self._open_login_url()
        elif command == "copy":
            self._show_login_url()
        elif command == "switch":
            self._selected_channel = self._resolve_channel_id(rest) or self._selected_channel
            self._switch_channel()
        elif command == "priority":
            self._handle_priority(rest)
        elif command == "exclude":
            self._handle_exclude(rest)
        elif command == "mode":
            self._handle_mode(rest)
        elif command == "filter":
            self._handle_filter(rest)
        elif command == "farm-unlinked":
            self._set_farm_unlinked(rest.lower() in {"1", "on", "true", "yes"})
        elif command == "help":
            self.print(
                "Commands: /dashboard /channels [next|prev] /drops [next|prev] "
                "/settings /logs /reload /switch <channel-id> /priority add <game> "
                "/exclude add <game> /mode <priority-only|ending-soonest|low-availability> "
                "/filter <expired|finished|excluded|upcoming|not-linked> <on|off> /quit"
            )
        else:
            self.print(f"Unknown command: {raw}")

    def _completion_candidates(self, command: str) -> list[str]:
        if command == "/priority add":
            existing = set(self.state.priority)
            return [game for game in self.state.available_games if game not in existing]
        if command == "/priority remove":
            return list(self.state.priority)
        if command == "/exclude add":
            existing = set(self.state.exclude)
            return [game for game in self.state.available_games if game not in existing]
        if command == "/exclude remove":
            return list(self.state.exclude)
        if command == "/switch":
            return [channel.name for channel in self.state.channels.values()]
        if command in {"/farm-unlinked", "/filter not-linked", "/filter upcoming", "/filter expired", "/filter excluded", "/filter finished"}:
            return ["on", "off"]
        if command == "/mode":
            return ["priority-only", "ending-soonest", "low-availability"]
        return []

    def _resolve_channel_id(self, value: str) -> str | None:
        value = value.strip()
        if not value:
            return None
        if value in self.state.channels:
            return value
        lowered = value.lower()
        for iid, channel in self.state.channels.items():
            if channel.name.lower() == lowered:
                return iid
        matches = [
            iid
            for iid, channel in self.state.channels.items()
            if channel.name.lower().startswith(lowered)
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            self.print(f"Channel name is ambiguous: {value}")
        else:
            self.print(f"Channel not found: {value}")
        return None

    def _scroll_channels(self, action: str) -> None:
        total = len(self.state.channels)
        if action in {"next", "down", "page-down"}:
            self._channel_offset = min(
                max(0, total - self.CHANNEL_PAGE_SIZE),
                self._channel_offset + self.CHANNEL_PAGE_SIZE,
            )
        elif action in {"prev", "up", "page-up"}:
            self._channel_offset = max(0, self._channel_offset - self.CHANNEL_PAGE_SIZE)

    def _scroll_campaigns(self, action: str) -> None:
        total = len(self._visible_campaigns())
        if action in {"next", "down", "page-down"}:
            self._campaign_offset = min(
                max(0, total - self.CAMPAIGN_PAGE_SIZE),
                self._campaign_offset + self.CAMPAIGN_PAGE_SIZE,
            )
        elif action in {"prev", "up", "page-up"}:
            self._campaign_offset = max(0, self._campaign_offset - self.CAMPAIGN_PAGE_SIZE)

    def _handle_priority(self, rest: str) -> None:
        action, _, game = rest.partition(" ")
        if action == "add":
            self._add_priority_game(game.strip())
        elif action == "remove":
            self._remove_priority_game(game.strip())
        else:
            self.print("Usage: /priority add <game> or /priority remove <game>")

    def _handle_exclude(self, rest: str) -> None:
        action, _, game = rest.partition(" ")
        if action == "add":
            self._add_exclude_game(game.strip())
        elif action == "remove":
            self._remove_exclude_game(game.strip())
        else:
            self.print("Usage: /exclude add <game> or /exclude remove <game>")

    def _handle_mode(self, mode: str) -> None:
        labels = {
            "priority-only": self.PRIORITY_MODE_LABELS[PriorityMode.PRIORITY_ONLY],
            "ending-soonest": self.PRIORITY_MODE_LABELS[PriorityMode.ENDING_SOONEST],
            "low-availability": self.PRIORITY_MODE_LABELS[PriorityMode.LOW_AVBL_FIRST],
        }
        if mode in labels:
            self._set_priority_mode(labels[mode])
        else:
            self.print("Modes: priority-only, ending-soonest, low-availability")

    def _handle_filter(self, rest: str) -> None:
        name, _, value = rest.partition(" ")
        filters = {
            "not-linked": "show_not_linked",
            "upcoming": "show_upcoming",
            "expired": "show_expired",
            "excluded": "show_excluded",
            "finished": "show_finished",
        }
        enabled = value.lower() in {"1", "on", "true", "yes", "show"}
        attr = filters.get(name)
        if attr is None or not value:
            self.print("Usage: /filter <not-linked|upcoming|expired|excluded|finished> <on|off>")
            return
        setattr(self.state.campaign_filters, attr, enabled)
        self._campaign_offset = 0
        self.print(f"Campaign filter {name} set to {'on' if enabled else 'off'}.")

    def _open_login_url(self) -> None:
        url = self.state.login.activation_url
        if url:
            webbrowser.open(url)
            self.print("Opened Twitch activation URL.")

    def _show_login_url(self) -> None:
        url = self.state.login.activation_url
        if url:
            self.print(f"Copy this Twitch activation URL: {url}")
        else:
            self.print("No Twitch activation URL is pending.")

    def set_games(self, games: set[Game]) -> None:
        super().set_games(games)
        self._channel_offset = 0
        self._campaign_offset = 0

    def _screen_fragments(self) -> AnyFormattedText:
        return [("class:screen", self._screen_text())]

    def _screen_text(self) -> str:
        width, height = self._terminal_size()
        lines = [
            self._title(width),
            self._tabs(width),
            "",
        ]
        if self.state.login.activation_url:
            lines.extend(self._login_lines(width))
        elif self._view == "channels":
            lines.extend(self._channels_lines(width))
        elif self._view == "drops":
            lines.extend(self._drops_lines(width))
        elif self._view == "settings":
            lines.extend(self._settings_lines(width))
        elif self._view == "logs":
            lines.extend(self._log_lines(width, height - len(lines) - 2))
        else:
            lines.extend(self._dashboard_lines(width, height - len(lines) - 2))
        return "\n".join(lines[: max(1, height - 2)])

    def _title(self, width: int) -> str:
        text = "TDMinER by HimanM"
        right = datetime.now().strftime("%H:%M:%S")
        if width < 48:
            return text[:width]
        gap = max(1, width - len(text) - len(right))
        return f"{text}{' ' * gap}{right}"[:width]

    def _tabs(self, width: int) -> str:
        tabs = ["dashboard", "drops", "channels", "settings", "logs"]
        parts = []
        for tab in tabs:
            parts.append(f"[{tab}]" if self._view == tab or tab == "dashboard" and self._view == "dashboard" else f" {tab} ")
        return " ".join(parts)[:width]

    def _dashboard_lines(self, width: int, available_height: int) -> list[str]:
        drop = self.state.current_drop
        watching = next((ch.name for ch in self.state.channels.values() if ch.watching), "-")
        websockets = sum(1 for ws in self.state.websockets.values() if "connected" in ws.status.lower())
        lines = [
            self._section("status", width),
            f"status        {self.state.status}",
            f"watching      {watching}",
            f"websockets    {websockets} connected",
            f"mode          {self.state.priority_mode}",
            f"farm unlinked {'on' if self.state.farm_unlinked else 'off'}",
            "",
            self._section("current drop", width),
            drop.game,
            drop.rewards,
            f"remaining     {drop.remaining}",
            self._bar("drop", drop.drop_progress, width),
            self._bar("campaign", drop.campaign_progress, width),
            "",
            self._section("logs", width),
        ]
        lines.extend(self.state.logs[-max(1, available_height - len(lines)) :] or ["No recent activity"])
        return [line[:width] for line in lines]

    def _channels_lines(self, width: int) -> list[str]:
        channels = list(self.state.channels.values())
        page = channels[self._channel_offset : self._channel_offset + self.CHANNEL_PAGE_SIZE]
        lines = [self._section(f"channels {self._page_label(self._channel_offset, self.CHANNEL_PAGE_SIZE, len(channels))}", width)]
        if width < 64:
            lines.append(f"{'':1} {'channel':24} {'status':10} {'drop':4}")
            for channel in page:
                marker = ">" if channel.watching else " "
                lines.append(f"{marker:1} {channel.name[:24]:24} {channel.status[:10]:10} {'yes' if channel.drops else 'no':4}")
        elif width < 92:
            lines.append(f"{'':1} {'channel':24} {'status':10} {'game':20} {'drop':4}")
            for channel in page:
                marker = ">" if channel.watching else " "
                lines.append(
                    f"{marker:1} {channel.name[:24]:24} {channel.status[:10]:10} {channel.game[:20]:20} {'yes' if channel.drops else 'no':4}"
                )
        else:
            lines.append(f"{'':1} {'channel':24} {'status':10} {'game':20} {'drop':4} {'viewers':8} {'acl':3}")
            for channel in page:
                marker = ">" if channel.watching else " "
                lines.append(
                    f"{marker:1} {channel.name[:24]:24} {channel.status[:10]:10} {channel.game[:20]:20} "
                    f"{'yes' if channel.drops else 'no':4} {channel.viewers[:8]:8} {'yes' if channel.acl_based else 'no':3}"
                )
        lines.append("Use /channels next or /channels prev.")
        return [line[:width] for line in lines]

    def _drops_lines(self, width: int) -> list[str]:
        campaigns = self._visible_campaigns()
        self._campaign_offset = min(self._campaign_offset, max(0, len(campaigns) - self.CAMPAIGN_PAGE_SIZE))
        page = campaigns[self._campaign_offset : self._campaign_offset + self.CAMPAIGN_PAGE_SIZE]
        lines = [self._section(f"drops {self._page_label(self._campaign_offset, self.CAMPAIGN_PAGE_SIZE, len(campaigns))}", width)]
        if width < 64:
            lines.append(f"{'game':22} {'status':10} {'progress':8}")
            for campaign in page:
                lines.append(f"{campaign.game[:22]:22} {campaign.status[:10]:10} {campaign.percent:8}")
        elif width < 92:
            lines.append(f"{'game':18} {'campaign':30} {'progress':8} {'drops':5}")
            for campaign in page:
                lines.append(f"{campaign.game[:18]:18} {campaign.name[:30]:30} {campaign.percent:8} {len(campaign.drops):5}")
        else:
            lines.append(f"{'game':18} {'campaign':32} {'status':10} {'linked':6} {'progress':8} {'drops':5}")
            for campaign in page:
                lines.append(
                    f"{campaign.game[:18]:18} {campaign.name[:32]:32} {campaign.status[:10]:10} "
                    f"{'yes' if campaign.linked else 'no':6} {campaign.percent:8} {len(campaign.drops):5}"
                )
        filters = self.state.campaign_filters
        lines.append(
            f"filters: not-linked={'on' if filters.show_not_linked else 'off'} "
            f"upcoming={'on' if filters.show_upcoming else 'off'} expired={'on' if filters.show_expired else 'off'} "
            f"excluded={'on' if filters.show_excluded else 'off'} finished={'on' if filters.show_finished else 'off'}"
        )
        return [line[:width] for line in lines]

    def _settings_lines(self, width: int) -> list[str]:
        lines = [
            self._section("settings", width),
            f"priority mode  {self.state.priority_mode}",
            f"farm unlinked  {'on' if self.state.farm_unlinked else 'off'}",
            f"available      {len(self.state.available_games)} games",
            f"priority       {', '.join(self.state.priority) or '-'}",
            f"exclude        {', '.join(self.state.exclude) or '-'}",
            "",
            "/priority add <game>  /exclude add <game>  /mode <name>",
            "/farm-unlinked on|off  (only works in priority-only mode)",
        ]
        return [line[:width] for line in lines]

    def _log_lines(self, width: int, available_height: int) -> list[str]:
        lines = [self._section("logs", width)]
        lines.extend(self.state.logs[-max(1, available_height - 1) :] or ["No recent activity"])
        return [line[:width] for line in lines]

    def _login_lines(self, width: int) -> list[str]:
        login = self.state.login
        lines = [
            self._section("login", width),
            "Twitch device login required",
            f"URL:  {login.activation_url}",
            f"Code: {login.user_code}",
            "Commands: /open /copy /quit",
        ]
        return [line[:width] for line in lines]

    def _bar(self, label: str, value: float, width: int) -> str:
        percent = max(0.0, min(1.0, value))
        bar_width = max(8, min(40, width - len(label) - 12))
        done = round(bar_width * percent)
        return f"{label:<9} [{'#' * done}{'-' * (bar_width - done)}] {percent:>5.1%}"

    @staticmethod
    def _section(label: str, width: int) -> str:
        text = f" {label} "
        side = max(0, (width - len(text)) // 2)
        return f"{'-' * side}{text}{'-' * max(0, width - side - len(text))}"

    @staticmethod
    def _terminal_size() -> tuple[int, int]:
        size = shutil.get_terminal_size((100, 28))
        return size.columns, size.lines

    def _visible_campaigns(self) -> list[CampaignSnapshot]:
        filters = self.state.campaign_filters
        campaigns = []
        for campaign in self.state.campaigns.values():
            if campaign.required_minutes <= 0:
                continue
            if not filters.show_not_linked and not campaign.linked:
                continue
            if campaign.upcoming and not filters.show_upcoming:
                continue
            if campaign.expired and not filters.show_expired:
                continue
            if campaign.excluded and not filters.show_excluded:
                continue
            if campaign.finished and not filters.show_finished:
                continue
            campaigns.append(campaign)
        return campaigns

    @staticmethod
    def _page_label(offset: int, page_size: int, total: int) -> str:
        if total == 0:
            return "(0/0)"
        start = offset + 1
        end = min(total, offset + page_size)
        return f"({start}-{end}/{total})"
