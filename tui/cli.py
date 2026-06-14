from __future__ import annotations

import asyncio
import webbrowser
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from core.constants import PriorityMode
from tui.manager import TUIManager
from tui.state import CampaignSnapshot, DropSnapshot

if TYPE_CHECKING:
    from core.utils import Game


class PortableCLIManager(TUIManager):
    """Prompt-based CLI frontend for terminals where the full Textual app is a poor fit."""

    CHANNEL_PAGE_SIZE = 10
    CAMPAIGN_PAGE_SIZE = 8

    def __init__(self, twitch: Any) -> None:
        super().__init__(twitch)
        self._view = "dashboard"
        self._channel_offset = 0
        self._campaign_offset = 0
        self._selected_channel: str | None = None
        self._console: Console | None = None
        self._command_task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._command_task is not None and not self._command_task.done():
            return
        self._app_ready.clear()
        self._console = Console()
        self._draw()
        self._command_task = asyncio.create_task(self._command_loop())
        self._app_ready.set()

    async def wait_until_ready(self) -> None:
        await self._app_ready.wait()

    def stop(self) -> None:
        super().stop()
        if self._command_task is not None:
            self._command_task.cancel()

    def close_window(self) -> None:
        self.stop()

    def close(self, *args: Any) -> int:
        result = super().close(*args)
        self.stop()
        return result

    def selected_channel_id(self) -> str | None:
        return self._selected_channel

    def refresh_status(self) -> None:
        return None

    def refresh_login(self) -> None:
        self._draw()

    def refresh_progress(self) -> None:
        return None

    def refresh_channels(self) -> None:
        return None

    def refresh_campaigns(self) -> None:
        return None

    def refresh_settings(self) -> None:
        return None

    async def _command_loop(self) -> None:
        while not self.close_requested:
            try:
                raw = await asyncio.to_thread(input, "tdminer> ")
            except (EOFError, KeyboardInterrupt):
                self.close()
                return
            self._handle_command(raw.strip())
            if not self.close_requested:
                self._draw()

    def _draw(self) -> None:
        if self._console is not None:
            self._console.rule("[bold bright_cyan]Twitch Drops Miner[/] [orange1]by HimanM[/]")
            self._console.print(self._render())

    @property
    def _terminal_width(self) -> int:
        if self._console is not None:
            return self._console.width
        return 120

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
            self._selected_channel = rest or self._selected_channel
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

    def _render(self) -> Group:
        header = self._header()
        if self.state.login.activation_url:
            body = self._login_view()
        elif self._view == "channels":
            body = self._channels_view()
        elif self._view == "drops":
            body = self._drops_view()
        elif self._view == "settings":
            body = self._settings_view()
        elif self._view == "logs":
            body = self._logs_view()
        else:
            body = self._dashboard_view()
        return Group(header, body, self._footer())

    def _header(self) -> Panel:
        logo = Text("TDMinER", style="bold bright_cyan")
        subtitle = Text(" by HimanM", style="bold orange1")
        status = Text(
            f"  |  {self.state.status}  |  {datetime.now().strftime('%H:%M:%S')}",
            style="bright_black",
        )
        title = Text.assemble(logo, subtitle, status)
        return Panel(title, box=box.SIMPLE_HEAVY, border_style="bright_cyan")

    def _footer(self) -> Panel:
        return Panel(
            Text(
                "/dashboard  /channels next|prev  /drops next|prev  /filter expired on  /reload  /quit",
                style="dim",
            ),
            box=box.SIMPLE,
            border_style="cyan",
        )

    def _login_view(self) -> Panel:
        login = self.state.login
        content = Text()
        content.append("Twitch device login required\n\n", style="bold cyan")
        content.append("Open this URL:\n", style="orange1")
        content.append(f"{login.activation_url}\n\n", style="bold white")
        content.append("Enter code:\n", style="orange1")
        content.append(f"{login.user_code}\n\n", style="bold cyan")
        content.append("Commands: /open, /copy, /quit", style="dim")
        return Panel(content, title="[bright_cyan]login[/]", border_style="bright_cyan")

    def _dashboard_view(self) -> Group:
        if self._terminal_width < 96:
            return Group(
                self._status_panel(),
                self._drop_panel(self.state.current_drop),
                self._recent_logs_panel(),
            )
        table = Table.grid(expand=True)
        table.add_column(ratio=1)
        table.add_column(ratio=2)
        table.add_row(self._status_panel(), self._drop_panel(self.state.current_drop))
        return Group(table, self._recent_logs_panel())

    def _status_panel(self) -> Panel:
        websockets = sum(1 for ws in self.state.websockets.values() if "connected" in ws.status.lower())
        watching = next((ch.name for ch in self.state.channels.values() if ch.watching), "-")
        lines = [
            ("status", self.state.status),
            ("watching", watching),
            ("websockets", f"{websockets} connected"),
            ("mode", self.state.priority_mode),
            ("farm unlinked", "on" if self.state.farm_unlinked else "off"),
        ]
        table = Table.grid(padding=(0, 2))
        table.add_column(style="cyan", no_wrap=True)
        table.add_column(style="white")
        for key, value in lines:
            table.add_row(key, value)
        return Panel(table, title="[bright_cyan]status[/]", border_style="bright_cyan")

    def _drop_panel(self, drop: DropSnapshot) -> Panel:
        progress = Progress(
            TextColumn("{task.description}", style="cyan"),
            BarColumn(bar_width=None),
            TextColumn("{task.percentage:>5.1f}%"),
            expand=True,
        )
        progress.add_task("drop", total=100, completed=drop.drop_progress * 100)
        progress.add_task("campaign", total=100, completed=drop.campaign_progress * 100)
        content = Group(
            Text(drop.game, style="bold white"),
            Text(drop.rewards, style="orange1"),
            Text(f"remaining {drop.remaining}", style="dim"),
            progress,
        )
        return Panel(content, title="[orange1]current drop[/]", border_style="orange1")

    def _channels_view(self) -> Panel:
        channels = list(self.state.channels.values())
        page = channels[self._channel_offset : self._channel_offset + self.CHANNEL_PAGE_SIZE]
        table = Table(box=box.SIMPLE_HEAVY, expand=True)
        if self._terminal_width < 64:
            columns = ("", "channel", "status", "drops")
        elif self._terminal_width < 90:
            columns = ("", "channel", "status", "game", "drops")
        else:
            columns = ("", "channel", "status", "game", "drops", "viewers", "acl")
        for column in columns:
            table.add_column(column, overflow="fold")
        for channel in page:
            marker = ">" if channel.watching else " "
            row = {
                "": marker,
                "channel": channel.name,
                "status": channel.status,
                "game": channel.game,
                "drops": "yes" if channel.drops else "no",
                "viewers": channel.viewers,
                "acl": "yes" if channel.acl_based else "no",
            }
            status = channel.status.lower()
            if channel.watching:
                style = "bold black on bright_cyan"
            elif "online" in status:
                style = "green"
            elif "pending" in status:
                style = "yellow"
            else:
                style = "dim"
            table.add_row(*(row[column] for column in columns), style=style)
        title = f"channels {self._page_label(self._channel_offset, self.CHANNEL_PAGE_SIZE, len(channels))}"
        hint = Text(
            f"Showing {len(page)} rows. Scroll with /channels next or /channels prev.",
            style="bright_black",
        )
        return Panel(Group(table, hint), title=f"[bright_cyan]{title}[/]", border_style="bright_cyan")

    def _drops_view(self) -> Panel:
        campaigns = self._visible_campaigns()
        self._campaign_offset = min(
            self._campaign_offset,
            max(0, len(campaigns) - self.CAMPAIGN_PAGE_SIZE),
        )
        page = campaigns[self._campaign_offset : self._campaign_offset + self.CAMPAIGN_PAGE_SIZE]
        table = Table(box=box.SIMPLE_HEAVY, expand=True)
        if self._terminal_width < 64:
            columns = ("game", "status", "progress")
        elif self._terminal_width < 92:
            columns = ("game", "campaign", "progress", "drops")
        else:
            columns = ("game", "campaign", "status", "linked", "progress", "drops")
        for column in columns:
            table.add_column(column, overflow="fold")
        for campaign in page:
            row = {
                "game": campaign.game,
                "campaign": campaign.name,
                "status": campaign.status,
                "linked": "yes" if campaign.linked else "no",
                "progress": campaign.percent,
                "drops": str(len(campaign.drops)),
            }
            table.add_row(
                *(row[column] for column in columns),
                style="green" if campaign.active else "yellow" if campaign.upcoming else "dim",
            )
        title = f"drops {self._page_label(self._campaign_offset, self.CAMPAIGN_PAGE_SIZE, len(campaigns))}"
        filter_bits = [
            f"not-linked={'on' if self.state.campaign_filters.show_not_linked else 'off'}",
            f"upcoming={'on' if self.state.campaign_filters.show_upcoming else 'off'}",
            f"expired={'on' if self.state.campaign_filters.show_expired else 'off'}",
            f"excluded={'on' if self.state.campaign_filters.show_excluded else 'off'}",
            f"finished={'on' if self.state.campaign_filters.show_finished else 'off'}",
        ]
        hint = Text(
            " | ".join(filter_bits)
            + "\nScroll with /drops next or /drops prev. Toggle with /filter expired on.",
            style="bright_black",
        )
        return Panel(Group(table, hint), title=f"[orange1]{title}[/]", border_style="orange1")

    def _settings_view(self) -> Panel:
        table = Table.grid(padding=(0, 3))
        table.add_column(style="cyan", no_wrap=True)
        table.add_column(style="white")
        table.add_row("priority mode", self.state.priority_mode)
        table.add_row("farm unlinked", "on" if self.state.farm_unlinked else "off")
        table.add_row("available games", str(len(self.state.available_games)))
        table.add_row("priority", ", ".join(self.state.priority) or "-")
        table.add_row("exclude", ", ".join(self.state.exclude) or "-")
        table.add_row("commands", "/priority add <game>  /exclude add <game>  /mode <name>")
        return Panel(table, title="[bright_cyan]settings[/]", border_style="bright_cyan")

    def _logs_view(self) -> Panel:
        return self._recent_logs_panel(limit=20)

    def _recent_logs_panel(self, *, limit: int = 8) -> Panel:
        logs = "\n".join(self.state.logs[-limit:]) or "No recent activity"
        return Panel(Text(logs, style="dim"), title="[bright_black]logs[/]", border_style="bright_black")

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
