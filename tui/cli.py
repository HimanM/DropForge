from __future__ import annotations

import os
import asyncio
import shutil
import time
import webbrowser
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING, Any, Callable

from prompt_toolkit.application import Application
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import has_completions
from prompt_toolkit.formatted_text import ANSI, AnyFormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box

from core.constants import PriorityMode
from tui.manager import TUIManager
from tui.state import CampaignSnapshot

if TYPE_CHECKING:
    from core.utils import Game


# ── Splash screen logo ───────────────────────────────────────────────
_LOGO = r"""
█▀█▄ █▀█▄ █▀██▀█▄ █ █▀█▄ █▀█▄ █▀█▄
  ▒█ ▒ ██ ▒ ██ ██ ▒ ▒ ██ ▒▄   ▒   
  ▓█ ▓▄██ ▓ ▀  ██ ▓ ▓ ██ ▓▄██ ▓     
By HimanM
"""

_SPLASH_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
_SPINNER_FRAMES = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"]

# ── Color palette ────────────────────────────────────────────────────
_C_CYAN = "#00d7ff"
_C_AMBER = "#ffaf00"
_C_GREEN = "#00d75f"
_C_RED = "#ff5f5f"
_C_YELLOW = "#ffd700"
_C_DIM = "#5f5f5f"
_C_TEXT = "#d7d7d7"
_C_BG = "#0a0a10"
_C_PANEL_BORDER = "#005f87"
_C_TAB_ACTIVE = "#00d7ff"
_C_TAB_INACTIVE = "#5f5f87"
_C_HEADER_BG = "#0f1520"


def _render_rich(rich_object: Any, width: int) -> str:
    console = Console(
        file=StringIO(),
        width=width,
        force_terminal=True,
        no_color=False,
    )
    console.print(rich_object)
    return console.file.getvalue()  # type: ignore[union-attr]


def _rich_to_pt(rich_object: Any, width: int) -> ANSI:
    ansi_text = _render_rich(rich_object, width)
    return ANSI(ansi_text)


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
    """Full-screen prompt_toolkit frontend with Rich styling for portable terminal sessions."""

    CHANNEL_PAGE_SIZE = 10
    CAMPAIGN_PAGE_SIZE = 8
    SPLASH_DURATION = 2.0
    ANIMATION_FPS = 12
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
        "/priority bump",
        "/priority demote",
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
        "/detach",
        "/help",
        "/help navigation",
        "/help control",
        "/help system",
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
        self._animation_task: asyncio.Task[None] | None = None
        self._spinner_tick = 0
        self._splash_start: float = 0.0
        self._splash_done = False
        self._transition_alpha = 0
        self._transition_target: str | None = None
        self._loading = False
        self._help_topic: str | None = None

    def start(self) -> None:
        if self._pt_app_task is not None and not self._pt_app_task.done():
            return
        self._app_ready.clear()
        self._pt_app = self._make_app()
        self._splash_start = time.monotonic()
        self._pt_app_task = asyncio.create_task(self._pt_app.run_async())
        self._clock_task = asyncio.create_task(self._clock_loop())
        self._animation_task = asyncio.create_task(self._animation_loop())
        self._app_ready.set()

    async def wait_until_ready(self) -> None:
        await self._app_ready.wait()

    def stop(self) -> None:
        super().stop()
        if self._clock_task is not None:
            self._clock_task.cancel()
        if self._animation_task is not None:
            self._animation_task.cancel()
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

    # ── App setup ────────────────────────────────────────────────────

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
                Window(height=1, char="\u2500", style="class:rule"),
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
                    "screen": f"ansidefault bg:{_C_BG}",
                    "rule": _C_DIM,
                    "frame.border": _C_CYAN,
                    "frame.label": f"bold {_C_AMBER}",
                    "prompt": f"bold {_C_CYAN}",
                    "completion-menu.completion": f"bg:#202028 {_C_TEXT}",
                    "completion-menu.completion.current": f"bg:#005f87 #ffffff bold",
                    "completion-menu.meta.completion": "bg:#202028 #878787",
                    "completion-menu.meta.completion.current": "bg:#005f87 #ffffff",
                }
            ),
        )

    # ── Animation loops ──────────────────────────────────────────────

    async def _clock_loop(self) -> None:
        while not self.close_requested:
            await asyncio.sleep(1)
            self._invalidate()

    async def _animation_loop(self) -> None:
        interval = 1.0 / self.ANIMATION_FPS
        while not self.close_requested:
            await asyncio.sleep(interval)
            self._spinner_tick += 1
            if self._transition_target is not None:
                self._transition_alpha = min(255, self._transition_alpha + 30)
            self._invalidate()

    def _invalidate(self) -> None:
        if self._pt_app is not None:
            self._pt_app.invalidate()

    def _spinner_char(self) -> str:
        return _SPINNER_FRAMES[self._spinner_tick % len(_SPINNER_FRAMES)]

    def _splash_spinner(self) -> str:
        return _SPLASH_FRAMES[self._spinner_tick % len(_SPLASH_FRAMES)]

    # ── Command handling ─────────────────────────────────────────────

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
            self._loading = True
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
        elif command == "detach":
            self._detach_tmux()
        elif command == "help":
            self._show_help(rest)
        else:
            self.print(f"Unknown command: {raw}")

    def _completion_candidates(self, command: str) -> list[str]:
        if command == "/priority add":
            existing = set(self.state.priority)
            return [game for game in self.state.available_games if game not in existing]
        if command in {"/priority remove", "/priority bump", "/priority demote"}:
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
        if command == "/help":
            return ["navigation", "control", "system"]
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
        elif action in {"bump", "up"}:
            self._move_priority_game(game.strip(), -1)
        elif action in {"demote", "down"}:
            self._move_priority_game(game.strip(), 1)
        else:
            self.print(
                "Usage: /priority add <game> | /priority remove <game> | /priority bump <game> | /priority demote <game>"
            )

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

    HELP_PAGES: dict[str, list[tuple[str, str]]] = {
        "navigation": [
            ("/dashboard", "Switch to the dashboard view (default)"),
            ("/channels", "Switch to the channels list view"),
            ("/channels next", "Page forward in the channels list"),
            ("/channels prev", "Page backward in the channels list"),
            ("/drops", "Switch to the drops/campaigns view"),
            ("/drops next", "Page forward in the drops list"),
            ("/drops prev", "Page backward in the drops list"),
            ("/settings", "Switch to the settings view"),
            ("/logs", "Switch to the logs view"),
        ],
        "control": [
            ("/reload", "Reload inventory and campaign data from Twitch"),
            ("/switch <channel>", "Switch to a specific channel by name or ID"),
            ("/priority add <game>", "Add a game to the priority list"),
            ("/priority remove <game>", "Remove a game from the priority list"),
            ("/priority bump <game>", "Move a game up in the priority list"),
            ("/priority demote <game>", "Move a game down in the priority list"),
            ("/exclude add <game>", "Add a game to the exclude list"),
            ("/exclude remove <game>", "Remove a game from the exclude list"),
            ("/mode <mode>", "Set priority mode: priority-only, ending-soonest, low-availability"),
            ("/filter <name> <on|off>", "Toggle filters: not-linked, upcoming, expired, excluded, finished"),
            ("/farm-unlinked on|off", "Enable/disable farming unlinked drops (priority-only mode)"),
        ],
        "system": [
            ("/open", "Open the Twitch login URL in a browser (when login is pending)"),
            ("/copy", "Show the Twitch login URL (when login is pending)"),
            ("/detach", "Detach from current tmux session (keeps miner running)"),
            ("/quit", "Exit the application"),
        ],
    }

    def _show_help(self, topic: str) -> None:
        topic = topic.strip().lower()
        if topic and topic in self.HELP_PAGES:
            self._help_topic = topic
            self._view = "help"
            return
        if topic:
            self.print(f"Unknown help topic: {topic}")
            return
        self._help_topic = None
        self._view = "help"

    def _rich_help(self, width: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        topic = getattr(self, "_help_topic", None)
        if topic and topic in self.HELP_PAGES:
            self._print_help_table(console, topic, self.HELP_PAGES[topic])
        else:
            console.print(f"[bold {_C_CYAN}]Help[/] — type /help <topic> for details\n")
            for name in self.HELP_PAGES:
                console.print(f"  [bold {_C_AMBER}]{name}[/]  ({len(self.HELP_PAGES[name])} commands)")
            console.print()
            console.print(f"[dim {_C_DIM}]  Examples: /help navigation, /help control, /help system[/]")
        return console.file.getvalue()  # type: ignore[union-attr]

    def _print_help_table(self, console: Console, title: str, commands: list[tuple[str, str]]) -> None:
        from rich.table import Table as RichTable
        from rich import box
        table = RichTable(
            title=f"[bold {_C_CYAN}]Help: {title.title()}[/]",
            box=box.SIMPLE_HEAVY,
            border_style=_C_PANEL_BORDER,
            show_header=True,
            padding=(0, 1),
            expand=True,
        )
        table.add_column("Command", style=f"bold {_C_AMBER}", min_width=24)
        table.add_column("Description", style=_C_TEXT)
        for cmd, desc in commands:
            table.add_row(cmd, desc)
        console.print(table)

    def _detach_tmux(self) -> None:
        import subprocess
        import shutil as _shutil
        if not _shutil.which("tmux"):
            self.print("tmux is not installed.")
            return
        env = os.environ.get("TMUX")
        if not env:
            self.print("Not running inside a tmux session.")
            return
        try:
            subprocess.run(["tmux", "detach-client"], check=False)
            self.print("Detached from tmux session.")
        except Exception as e:
            self.print(f"Failed to detach: {e}")

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

    # ── Rich rendering ───────────────────────────────────────────────

    def _screen_fragments(self) -> AnyFormattedText:
        width, height = self._terminal_size()
        ansi_text = self._render_screen(width, height)
        return ANSI(ansi_text)

    def _render_screen(self, width: int, height: int) -> str:
        now = time.monotonic()
        elapsed = now - self._splash_start
        if not self._splash_done and elapsed < self.SPLASH_DURATION:
            return self._render_splash(width, height, elapsed)
        self._splash_done = True
        if self.state.login.activation_url:
            return self._render_login(width, height)
        lines = [
            self._rich_title(width),
            self._rich_tabs(width),
        ]
        view_text = ""
        if self._view == "channels":
            view_text = self._rich_channels(width)
        elif self._view == "drops":
            view_text = self._rich_drops(width)
        elif self._view == "settings":
            view_text = self._rich_settings(width)
        elif self._view == "logs":
            view_text = self._rich_logs(width, height - 4)
        elif self._view == "help":
            view_text = self._rich_help(width)
        else:
            view_text = self._rich_dashboard(width, height - 4)
        lines.append(view_text)
        joined = "\n".join(lines)
        return joined[: height * width]

    # ── Test compatibility wrappers ──────────────────────────────────

    @staticmethod
    def _strip_ansi(text: str) -> str:
        import re
        return re.sub(r"\x1b\[[0-9;]*m", "", text)

    def _screen_text(self) -> str:
        width, height = self._terminal_size()
        return self._strip_ansi(self._render_screen(width, height))

    def _channels_lines(self, width: int) -> list[str]:
        return self._strip_ansi(self._rich_channels(width)).splitlines()

    def _drops_lines(self, width: int) -> list[str]:
        return self._strip_ansi(self._rich_drops(width)).splitlines()

    # ── Splash screen ────────────────────────────────────────────────

    def _render_splash(self, width: int, height: int, elapsed: float) -> str:
        spinner = self._splash_spinner()
        progress = min(1.0, elapsed / self.SPLASH_DURATION)
        bar_width = max(10, min(40, width - 10))
        filled = round(bar_width * progress)
        bar = f"[{'#' * filled}{'-' * (bar_width - filled)}]"
        console = Console(file=StringIO(), width=width, force_terminal=True)
        console.print()
        if width >= 50:
            logo_text = _LOGO.strip("\n")
            console.print(
                Text(logo_text, style=f"bold {_C_CYAN}"),
                justify="center",
            )
            console.print()
            console.print(
                Text("Twitch Drops Miner", style=f"bold {_C_AMBER}"),
                justify="center",
            )
        else:
            console.print(
                Text("TDMinER", style=f"bold {_C_CYAN}"),
                justify="center",
            )
            console.print(
                Text("by HimanM", style=_C_DIM),
                justify="center",
            )
        console.print()
        status = f"  {spinner} Loading{'.' * ((self._spinner_tick // 4) % 4)}"
        console.print(Text(status, style=_C_TEXT))
        console.print()
        console.print(
            Text(f"  {bar}  {progress:.0%}", style=_C_GREEN),
        )
        console.print()
        console.print(
            Text("  Press any key to skip...", style=_C_DIM),
            justify="center",
        )
        result = console.file.getvalue()  # type: ignore[union-attr]
        return result

    # ── Title & tabs ─────────────────────────────────────────────────

    def _rich_title(self, width: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        right = datetime.now().strftime("%H:%M:%S")
        title = Text()
        title.append("TDMinER ", style=f"bold {_C_CYAN}")
        title.append("by HimanM", style=_C_DIM)
        padding = max(1, width - len("TDMinER by HimanM") - len(right) - 2)
        title.append(" " * padding)
        title.append(right, style=_C_DIM)
        console.print(title)
        return console.file.getvalue().rstrip("\n")  # type: ignore[union-attr]

    def _rich_tabs(self, width: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        tabs = ["dashboard", "drops", "channels", "settings", "logs", "help"]
        t = Text()
        for i, tab in enumerate(tabs):
            if i > 0:
                t.append("  ")
            if tab == self._view:
                t.append(f"[{tab}]", style=f"bold {_C_TAB_ACTIVE}")
            else:
                t.append(f" {tab} ", style=_C_TAB_INACTIVE)
        console.print(t)
        return console.file.getvalue().rstrip("\n")  # type: ignore[union-attr]

    # ── Dashboard view ───────────────────────────────────────────────

    def _rich_dashboard(self, width: int, available_height: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        drop = self.state.current_drop
        watching = next((ch.name for ch in self.state.channels.values() if ch.watching), "-")
        websockets = sum(1 for ws in self.state.websockets.values() if "connected" in ws.status.lower())
        spinner = self._spinner_char()
        narrow = width < 60

        # Status panel
        status_table = Table(show_header=False, box=None, padding=(0, 1))
        status_table.add_column(style=_C_DIM, width=14)
        status_table.add_column()
        status_icon = _status_icon(self.state.status)
        status_table.add_row("Status", Text(f"{status_icon} {self.state.status}", style=_C_TEXT))
        if not narrow:
            status_table.add_row("Watching", Text(watching, style=_C_CYAN if watching != "-" else _C_DIM))
        status_table.add_row("Websockets", Text(f"{spinner} {websockets} connected", style=_C_GREEN if websockets > 0 else _C_YELLOW))
        status_table.add_row("Mode", Text(self.state.priority_mode, style=_C_AMBER))
        status_table.add_row("Farm unlinked", Text("on" if self.state.farm_unlinked else "off", style=_C_GREEN if self.state.farm_unlinked else _C_DIM))

        status_panel = Panel(status_table, title=f"[bold {_C_CYAN}]Status[/]", border_style=_C_PANEL_BORDER)

        # Drop progress panel
        drop_table = Table(show_header=False, box=None, padding=(0, 1))
        drop_table.add_column(style=_C_DIM, width=14)
        drop_table.add_column()
        drop_table.add_row("Game", Text(drop.game, style="bold"))
        if not narrow:
            drop_table.add_row("Rewards", Text(drop.rewards, style=_C_AMBER))
        drop_table.add_row("Remaining", Text(drop.remaining, style=_C_YELLOW))

        bar_width = max(8, min(30, width - 20))
        drop_bar = self._rich_progress_bar(drop.drop_progress, width=bar_width, label="Drop")
        campaign_bar = self._rich_progress_bar(drop.campaign_progress, width=bar_width, label="Campaign")

        progress_content = Table(show_header=False, box=None)
        progress_content.add_column()
        progress_content.add_row(drop_table)
        progress_content.add_row(Text())
        progress_content.add_row(drop_bar)
        progress_content.add_row(Text())
        progress_content.add_row(campaign_bar)

        progress_panel = Panel(progress_content, title=f"[bold {_C_AMBER}]Current Drop[/]", border_style=_C_PANEL_BORDER)

        if narrow:
            console.print(status_panel)
            console.print(progress_panel)
        else:
            from rich.columns import Columns as RichColumns
            panels = RichColumns([status_panel, progress_panel], padding=1, expand=False)
            console.print(panels)

        # Logs section
        console.print(f"[bold {_C_DIM}]{'─' * width}[/]")
        console.print(f"[bold {_C_AMBER}]Logs[/]")
        logs = self.state.logs[-max(1, available_height - 12):] or ["No recent activity"]
        for line in logs:
            console.print(f"  {_dim_log(line)}")

        return console.file.getvalue()  # type: ignore[union-attr]

    # ── Channels view ────────────────────────────────────────────────

    def _rich_channels(self, width: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        channels = list(self.state.channels.values())
        page = channels[self._channel_offset : self._channel_offset + self.CHANNEL_PAGE_SIZE]
        total = len(channels)
        page_label = self._page_label(self._channel_offset, self.CHANNEL_PAGE_SIZE, total)

        table = Table(
            title=f"[bold {_C_CYAN}]Channels[/] {page_label}",
            box=box.ROUNDED,
            border_style=_C_PANEL_BORDER,
            title_style=_C_CYAN,
            show_lines=False,
            expand=True,
        )
        table.add_column("", width=2, justify="center")
        table.add_column("Channel", style="bold", max_width=24)
        table.add_column("Status", width=10)
        table.add_column("Game", max_width=20)
        table.add_column("Drop", width=5, justify="center")
        if width >= 92:
            table.add_column("Viewers", width=8, justify="right")
            table.add_column("ACL", width=4, justify="center")

        for channel in page:
            status_style = _channel_status_style(channel.status)
            if channel.watching:
                marker = Text()
                marker.append("> ", style=f"bold {_C_GREEN}")
            else:
                marker = Text("  ")
            row = [
                marker,
                Text(channel.name, style="bold" if channel.watching else ""),
                Text(channel.status, style=status_style),
                Text(channel.game[:20], style=_C_TEXT),
                Text("yes" if channel.drops else "no", style=_C_GREEN if channel.drops else _C_RED),
            ]
            if width >= 92:
                row.append(Text(channel.viewers[:8], style=_C_TEXT))
                row.append(Text("yes" if channel.acl_based else "no", style=_C_GREEN if channel.acl_based else _C_DIM))
            table.add_row(*row)

        console.print(table)
        console.print(f"[dim {_C_DIM}]  Use /channels next or /channels prev to navigate.[/]")
        return console.file.getvalue()  # type: ignore[union-attr]

    # ── Drops/Campaigns view ─────────────────────────────────────────

    def _rich_drops(self, width: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        campaigns = self._visible_campaigns()
        self._campaign_offset = min(self._campaign_offset, max(0, len(campaigns) - self.CAMPAIGN_PAGE_SIZE))
        page = campaigns[self._campaign_offset : self._campaign_offset + self.CAMPAIGN_PAGE_SIZE]
        total = len(campaigns)
        page_label = self._page_label(self._campaign_offset, self.CAMPAIGN_PAGE_SIZE, total)

        narrow = width < 60
        medium = width < 72

        table = Table(
            title=f"[bold {_C_AMBER}]Drops[/] {page_label}",
            box=box.ROUNDED,
            border_style=_C_PANEL_BORDER,
            title_style=_C_AMBER,
            show_lines=False,
            expand=True,
        )
        table.add_column("Game", style="bold", max_width=18 if not narrow else 14)
        if not narrow:
            table.add_column("Campaign", max_width=26 if not medium else 18)
        table.add_column("Status", width=10 if not narrow else 8)
        if not narrow:
            table.add_column("Linked", width=6, justify="center")
        table.add_column("Progress", width=12)
        if width >= 92:
            table.add_column("Allowed", max_width=24)

        for campaign in page:
            status_style = _campaign_status_style(campaign)
            linked_style = _C_GREEN if campaign.linked else _C_RED
            progress_bar = self._rich_mini_bar(campaign.progress, width=6 if narrow else 8)
            row = [
                Text(campaign.game[:18 if not narrow else 14], style="bold"),
            ]
            if not narrow:
                row.append(Text(campaign.name[:26 if not medium else 18]))
            row.append(Text(campaign.status, style=status_style))
            if not narrow:
                row.append(Text("yes" if campaign.linked else "no", style=linked_style))
            row.append(Text(f"{progress_bar} {campaign.percent}", style=_C_TEXT))
            if width >= 92:
                row.append(Text(campaign.allowed_channels[:24], style=_C_DIM))
            table.add_row(*row)

        console.print(table)
        filters = self.state.campaign_filters
        filter_text = Text()
        filter_text.append("filters: ", style=_C_DIM)
        for name, val in [
            ("not-linked", filters.show_not_linked),
            ("upcoming", filters.show_upcoming),
            ("expired", filters.show_expired),
            ("excluded", filters.show_excluded),
            ("finished", filters.show_finished),
        ]:
            state = "on" if val else "off"
            style = _C_GREEN if val else _C_DIM
            filter_text.append(f"{name}={state} ", style=style)
        console.print(filter_text)
        return console.file.getvalue()  # type: ignore[union-attr]

    # ── Settings view ────────────────────────────────────────────────

    def _rich_settings(self, width: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)

        table = Table(
            title=f"[bold {_C_GREEN}]Settings[/]",
            box=box.ROUNDED,
            border_style=_C_PANEL_BORDER,
            title_style=_C_GREEN,
            show_header=False,
            padding=(0, 2),
        )
        table.add_column(style=_C_DIM, width=16)
        table.add_column()
        table.add_row("Mode", Text(self.state.priority_mode, style=_C_AMBER))
        table.add_row("Farm unlinked", Text("on" if self.state.farm_unlinked else "off", style=_C_GREEN if self.state.farm_unlinked else _C_DIM))
        table.add_row("Available", Text(f"{len(self.state.available_games)} games", style=_C_TEXT))

        console.print(table)

        has_priority = bool(self.state.priority)
        has_exclude = bool(self.state.exclude)
        side_by_side = width >= 64 and has_priority and has_exclude

        if side_by_side:
            from rich.columns import Columns as RichColumns
            panels = []
            ptable = Table(
                title=f"[bold {_C_CYAN}]Priority List[/]",
                box=box.SIMPLE,
                border_style=_C_PANEL_BORDER,
                show_header=True,
            )
            ptable.add_column("#", width=3, style=_C_DIM)
            ptable.add_column("Game", style="bold")
            for idx, game in enumerate(self.state.priority, start=1):
                ptable.add_row(str(idx), game)
            panels.append(ptable)

            etable = Table(
                title=f"[bold {_C_RED}]Exclude List[/]",
                box=box.SIMPLE,
                border_style=_C_PANEL_BORDER,
                show_header=True,
            )
            etable.add_column("Game", style="bold")
            for game in self.state.exclude:
                etable.add_row(game)
            panels.append(etable)

            console.print()
            console.print(RichColumns(panels, padding=2, expand=False))
        else:
            if has_priority:
                console.print()
                ptable = Table(
                    title=f"[bold {_C_CYAN}]Priority List[/]",
                    box=box.SIMPLE,
                    border_style=_C_PANEL_BORDER,
                    show_header=True,
                )
                ptable.add_column("#", width=3, style=_C_DIM)
                ptable.add_column("Game", style="bold")
                for idx, game in enumerate(self.state.priority, start=1):
                    ptable.add_row(str(idx), game)
                console.print(ptable)

            if has_exclude:
                console.print()
                etable = Table(
                    title=f"[bold {_C_RED}]Exclude List[/]",
                    box=box.SIMPLE,
                    border_style=_C_PANEL_BORDER,
                    show_header=True,
                )
                etable.add_column("Game", style="bold")
                for game in self.state.exclude:
                    etable.add_row(game)
                console.print(etable)

        console.print()
        console.print(Text("  /priority add <game>  /priority remove <game>", style=_C_DIM))
        console.print(Text("  /priority bump <game>  /priority demote <game>", style=_C_DIM))
        console.print(Text("  /exclude add <game>  /mode <name>", style=_C_DIM))
        console.print(Text("  /farm-unlinked on|off  (only works in priority-only mode)", style=_C_DIM))

        return console.file.getvalue()  # type: ignore[union-attr]

    # ── Logs view ────────────────────────────────────────────────────

    def _rich_logs(self, width: int, available_height: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        console.print(f"[bold {_C_AMBER}]Logs[/]")
        logs = self.state.logs[-max(1, available_height):] or ["No recent activity"]
        for line in logs:
            console.print(f"  {_dim_log(line)}")
        return console.file.getvalue()  # type: ignore[union-attr]

    # ── Login view ───────────────────────────────────────────────────

    def _render_login(self, width: int, height: int) -> str:
        console = Console(file=StringIO(), width=width, force_terminal=True)
        login = self.state.login
        spinner = self._spinner_char()

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column(style=_C_DIM, width=8)
        table.add_column()
        table.add_row("Status", Text(login.status, style=_C_YELLOW))
        table.add_row("User", Text(login.user_id, style=_C_TEXT))
        table.add_row("Code", Text(login.user_code, style=f"bold {_C_YELLOW}"))

        url_text = Text()
        url_text.append("URL: ", style=_C_DIM)
        url_text.append(login.activation_url, style=f"bold {_C_CYAN}")

        content = Table(show_header=False, box=None)
        content.add_column()
        content.add_row(table)
        content.add_row(Text())
        content.add_row(url_text)
        content.add_row(Text())
        content.add_row(Text(f"  {spinner} Waiting for activation...", style=_C_AMBER))
        content.add_row(Text())
        content.add_row(Text("  Commands: /open  /copy  /quit", style=_C_DIM))

        panel = Panel(
            content,
            title=f"[bold {_C_YELLOW}]Twitch Login Required[/]",
            border_style=_C_YELLOW,
            padding=(1, 2),
        )
        console.print(panel)
        return console.file.getvalue()  # type: ignore[union-attr]

    # ── Rich progress bar helpers ────────────────────────────────────

    def _rich_progress_bar(self, value: float, width: int = 30, label: str = "") -> Text:
        percent = max(0.0, min(1.0, value))
        filled = round(width * percent)
        empty = width - filled
        bar = Text()
        if label:
            bar.append(f"{label:<9} ", style=_C_DIM)
        bar.append("[", style=_C_DIM)
        bar.append("\u2588" * filled, style=_progress_color(percent))
        bar.append("\u2500" * empty, style="#2a2a2a")
        bar.append("] ", style=_C_DIM)
        bar.append(f"{percent:>6.1%}", style=_progress_color(percent))
        return bar

    def _rich_mini_bar(self, value: float, width: int = 8) -> Text:
        percent = max(0.0, min(1.0, value))
        filled = round(width * percent)
        empty = width - filled
        bar = Text()
        bar.append("[", style=_C_DIM)
        bar.append("\u2588" * filled, style=_progress_color(percent))
        bar.append("\u2500" * empty, style="#2a2a2a")
        bar.append("]", style=_C_DIM)
        return bar

    # ── Misc helpers ─────────────────────────────────────────────────

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


# ── Module-level helpers ──────────────────────────────────────────────

def _status_icon(status: str) -> str:
    s = status.lower()
    if "running" in s or "watching" in s or "connected" in s:
        return "\u25cf"  # green circle (via style)
    if "idle" in s or "waiting" in s or "pending" in s:
        return "\u25cb"  # yellow circle
    if "error" in s or "failed" in s:
        return "\u25cf"  # red circle
    return "\u25cb"  # default


def _channel_status_style(status: str) -> str:
    s = status.lower()
    if "online" in s:
        return _C_GREEN
    if "pending" in s:
        return _C_YELLOW
    return _C_RED


def _campaign_status_style(campaign: CampaignSnapshot) -> str:
    if campaign.active:
        return _C_GREEN
    if campaign.upcoming:
        return _C_CYAN
    if campaign.expired:
        return _C_RED
    return _C_DIM


def _progress_color(percent: float) -> str:
    if percent >= 0.75:
        return _C_GREEN
    if percent >= 0.40:
        return _C_YELLOW
    return _C_RED


def _dim_log(line: str) -> str:
    return f"[{_C_DIM}]{line}[/]"
