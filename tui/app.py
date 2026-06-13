from __future__ import annotations

import webbrowser
from collections import abc
from typing import TypeVar

from textual.app import App, ComposeResult, ScreenStackError
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets._button import Button
from textual.widgets._data_table import DataTable
from textual.widgets._footer import Footer
from textual.widgets._header import Header
from textual.widgets._input import Input
from textual.widgets._label import Label
from textual.widgets._log import Log
from textual.widgets._progress_bar import ProgressBar
from textual.widgets._static import Static
from textual.widgets._tabbed_content import TabbedContent, TabPane

from core.constants import State
from tui.state import TUIState, clamp_progress


_WidgetT = TypeVar("_WidgetT", bound=Widget)


class TwitchDropsTUI(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }

    #dashboard {
        layout: vertical;
    }

    #summary-row {
        height: auto;
    }

    .panel {
        border: round $accent;
        padding: 1;
        margin: 0 1 1 0;
        min-width: 24;
    }

    .grow {
        width: 1fr;
    }

    .stack {
        height: auto;
    }

    #progress-panel {
        min-width: 38;
    }

    #drop-bar,
    #campaign-bar {
        width: 100%;
        margin-top: 1;
    }

    #dashboard-log {
        height: 1fr;
        border: round $surface;
    }

    DataTable {
        height: 1fr;
    }

    #login-actions {
        height: auto;
        margin-top: 1;
    }

    #login-actions Button {
        margin-right: 1;
    }

    Input {
        margin-bottom: 1;
    }

    #logs-tab Log {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("q", "request_quit", "Quit"),
        ("r", "reload", "Reload"),
        ("s", "switch_channel", "Switch"),
        ("b", "open_browser", "Open Browser"),
        ("c", "copy_login_url", "Copy Login URL"),
    ]

    def __init__(
        self,
        state: TUIState,
        *,
        on_close: abc.Callable[[], None],
        on_reload: abc.Callable[[], None],
        login_confirm: asyncio_event_setter,
        on_switch: abc.Callable[[], None],
        on_save_settings: abc.Callable[[str, str], None],
        on_cycle_priority_mode: abc.Callable[[], None],
        on_toggle_farm_unlinked: abc.Callable[[], None],
    ) -> None:
        super().__init__()
        self.state = state
        self._on_close = on_close
        self._on_reload = on_reload
        self._login_confirm = login_confirm
        self._on_switch = on_switch
        self._on_save_settings = on_save_settings
        self._on_cycle_priority_mode = on_cycle_priority_mode
        self._on_toggle_farm_unlinked = on_toggle_farm_unlinked

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="dashboard-tab"):
            with TabPane("Dashboard", id="dashboard-tab"):
                with Vertical(id="dashboard"):
                    with Horizontal(id="summary-row"):
                        with Vertical(classes="panel grow"):
                            yield Label("Status")
                            yield Static("", id="status-text")
                            yield Label("Login")
                            yield Static("", id="login-text")
                            yield Static("", id="login-url")
                            with Horizontal(id="login-actions"):
                                yield Button("Open browser", id="open-browser")
                                yield Button("Copy URL", id="copy-url")
                                yield Button("Continue", id="login-continue")
                        with Vertical(id="progress-panel", classes="panel grow"):
                            yield Label("Current drop")
                            yield Static("", id="drop-title")
                            yield Static("", id="drop-remaining")
                            yield ProgressBar(total=100, id="drop-bar")
                            yield Label("Campaign")
                            yield Static("", id="campaign-title")
                            yield ProgressBar(total=100, id="campaign-bar")
                    yield Log(id="dashboard-log", highlight=True)
            with TabPane("Campaigns", id="campaigns-tab"):
                yield DataTable(id="campaigns-table")
            with TabPane("Channels", id="channels-tab"):
                yield DataTable(id="channels-table")
            with TabPane("Settings", id="settings-tab"):
                with VerticalScroll(classes="panel"):
                    yield Static("", id="settings-text")
                    yield Label("Priority games, comma-separated")
                    yield Input(placeholder="Game one, Game two", id="priority-input")
                    yield Label("Excluded games, comma-separated")
                    yield Input(placeholder="Game one, Game two", id="exclude-input")
                    with Horizontal(id="settings-actions"):
                        yield Button("Save lists", id="save-settings")
                        yield Button("Cycle priority mode", id="cycle-priority")
                        yield Button("Toggle farm unlinked", id="toggle-farm-unlinked")
                    yield Button("Reload inventory", id="reload")
            with TabPane("Logs", id="logs-tab"):
                yield Log(id="full-log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Twitch Drops Miner TUI"
        self.sub_title = "tdminer"
        self._setup_tables()
        self.refresh_all()

    def _setup_tables(self) -> None:
        campaigns = self.query_one("#campaigns-table", DataTable)
        campaigns.zebra_stripes = True
        campaigns.add_columns("Game", "Campaign", "Status", "Linked", "Progress", "Drops")

        channels = self.query_one("#channels-table", DataTable)
        channels.zebra_stripes = True
        channels.cursor_type = "row"
        channels.add_columns("Channel", "Status", "Game", "Drops", "Viewers", "ACL")

    def _refresh_later(self, callback: abc.Callable[[], None]) -> None:
        if self.is_running and self.is_mounted:
            self.call_next(callback)

    def _widget(self, selector: str, widget_type: type[_WidgetT]) -> _WidgetT | None:
        try:
            return self.query_one(selector, widget_type)
        except (NoMatches, ScreenStackError):
            return None

    def refresh_all(self) -> None:
        self.refresh_status()
        self.refresh_login()
        self.refresh_progress()
        self.refresh_channels()
        self.refresh_campaigns()
        self.refresh_settings(sync_inputs=True)
        self.refresh_logs()

    def refresh_status_later(self) -> None:
        self._refresh_later(self.refresh_status)

    def refresh_login_later(self) -> None:
        self._refresh_later(self.refresh_login)

    def refresh_progress_later(self) -> None:
        self._refresh_later(self.refresh_progress)

    def refresh_channels_later(self) -> None:
        self._refresh_later(self.refresh_channels)

    def refresh_campaigns_later(self) -> None:
        self._refresh_later(self.refresh_campaigns)

    def refresh_settings_later(self) -> None:
        self._refresh_later(lambda: self.refresh_settings(sync_inputs=True))

    def append_log_later(self, line: str) -> None:
        if self.is_running and self.is_mounted:
            self.call_next(lambda: self.append_log(line))

    def append_log(self, line: str) -> None:
        dashboard_log = self._widget("#dashboard-log", Log)
        full_log = self._widget("#full-log", Log)
        if dashboard_log is not None:
            dashboard_log.write_line(line)
        if full_log is not None:
            full_log.write_line(line)

    def refresh_logs(self) -> None:
        for line in self.state.logs[-100:]:
            self.append_log(line)

    def refresh_status(self) -> None:
        status = self._widget("#status-text", Static)
        if status is not None:
            status.update(f"{self.state.status}\nMode: {self.state.icon_state}")

    def refresh_login(self) -> None:
        login = self.state.login
        login_text = self._widget("#login-text", Static)
        login_url = self._widget("#login-url", Static)
        if login_text is not None:
            login_text.update(f"{login.status}\nUser: {login.user_id}")
        if login_url is not None:
            if login.activation_url:
                login_url.update(f"URL: {login.activation_url}\nCode: {login.user_code}")
            else:
                login_url.update("")

    def refresh_progress(self) -> None:
        drop = self.state.current_drop
        drop_title = self._widget("#drop-title", Static)
        drop_remaining = self._widget("#drop-remaining", Static)
        drop_bar = self._widget("#drop-bar", ProgressBar)
        campaign_title = self._widget("#campaign-title", Static)
        campaign_bar = self._widget("#campaign-bar", ProgressBar)
        if drop_title is not None:
            drop_title.update(f"{drop.game}\n{drop.rewards} ({drop.drop_percent})")
        if drop_remaining is not None:
            drop_remaining.update(f"Remaining: {drop.remaining}")
        if drop_bar is not None:
            drop_bar.update(progress=clamp_progress(drop.drop_progress) * 100)
        if campaign_title is not None:
            campaign_title.update(f"{drop.campaign} ({drop.campaign_percent})")
        if campaign_bar is not None:
            campaign_bar.update(progress=clamp_progress(drop.campaign_progress) * 100)

    def refresh_channels(self) -> None:
        table = self._widget("#channels-table", DataTable)
        if table is None:
            return
        table.clear()
        for channel in self.state.channels.values():
            label = f"> {channel.name}" if channel.watching else channel.name
            row = (label, *channel.row[1:])
            table.add_row(*row, key=channel.iid)

    def refresh_campaigns(self) -> None:
        table = self._widget("#campaigns-table", DataTable)
        if table is None:
            return
        table.clear()
        for campaign in self.state.campaigns.values():
            table.add_row(
                campaign.game,
                campaign.name,
                campaign.status,
                "yes" if campaign.linked else "no",
                campaign.percent,
                "\n".join(campaign.drops),
                key=campaign.id,
            )

    def refresh_settings(self, *, sync_inputs: bool = False) -> None:
        settings = self._widget("#settings-text", Static)
        if settings is not None:
            settings.update(self.state.settings_text)
        if sync_inputs:
            priority = self._widget("#priority-input", Input)
            exclude = self._widget("#exclude-input", Input)
            if priority is not None:
                priority.value = ", ".join(self.state.priority)
            if exclude is not None:
                exclude.value = ", ".join(self.state.exclude)

    def selected_channel_id(self) -> str | None:
        table = self._widget("#channels-table", DataTable)
        if table is None:
            return None
        if table.row_count == 0 or table.cursor_row < 0:
            return None
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        except Exception:
            return None
        if row_key is None:
            return None
        return str(row_key.value)

    def action_request_quit(self) -> None:
        self._on_close()

    def action_reload(self) -> None:
        self._on_reload()

    def action_switch_channel(self) -> None:
        self._on_switch()

    def action_open_browser(self) -> None:
        self.open_activation_url()

    def action_copy_login_url(self) -> None:
        self.copy_activation_url()

    def open_activation_url(self) -> None:
        url = self.state.login.activation_url
        if url:
            webbrowser.open(url)
            self.notify("Opened login URL in browser")

    def copy_activation_url(self) -> None:
        url = self.state.login.activation_url
        if url:
            self.copy_to_clipboard(url)
            self.notify("Copied login URL")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "open-browser":
            self.open_activation_url()
        elif button_id == "copy-url":
            self.copy_activation_url()
        elif button_id == "login-continue":
            self._login_confirm()
        elif button_id == "reload":
            self._on_reload()
        elif button_id == "save-settings":
            self._on_save_settings(
                self.query_one("#priority-input", Input).value,
                self.query_one("#exclude-input", Input).value,
            )
        elif button_id == "cycle-priority":
            self._on_cycle_priority_mode()
        elif button_id == "toggle-farm-unlinked":
            self._on_toggle_farm_unlinked()


asyncio_event_setter = abc.Callable[[], None]
