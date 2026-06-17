from __future__ import annotations

import webbrowser
from collections import abc
from typing import Any, TypeVar

from textual.app import App, ComposeResult, ScreenStackError
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Checkbox, Select
from textual.widgets._button import Button
from textual.widgets._data_table import DataTable
from textual.widgets._footer import Footer
from textual.widgets._header import Header
from textual.widgets._label import Label
from textual.widgets._log import Log
from textual.widgets._progress_bar import ProgressBar
from textual.widgets._static import Static
from textual.widgets._tabbed_content import TabbedContent, TabPane

from core.constants import State
from tui.state import TUIState, clamp_progress


_WidgetT = TypeVar("_WidgetT", bound=Widget)


class TwitchDropsTUI(App[None]):
    PRIORITY_MODE_OPTIONS = (
        ("Priority list only", "Priority list only"),
        ("Ending soonest", "Ending soonest"),
        ("Low availability first", "Low availability first"),
    )

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

    #settings-grid {
        height: 1fr;
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

    .compact-panel {
        border: round $surface;
        padding: 0 1;
        margin: 0 1 1 0;
        min-width: 22;
    }

    .filter-strip,
    .action-row {
        height: auto;
        margin-bottom: 1;
    }

    #filter-label {
        width: auto;
        margin-right: 1;
    }

    .filter-strip Checkbox {
        width: auto;
    }

    .action-row Button,
    .filter-strip Checkbox {
        margin-right: 1;
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

    Button {
        min-width: 7;
        width: auto;
        padding: 0 1;
    }

    Select {
        margin-bottom: 1;
    }

    #logs-tab Log {
        height: 1fr;
    }
    """

    BINDINGS = [
        ("q", "request_quit", "Quit"),
        ("ctrl+q", "request_quit", "Quit"),
        ("ctrl+c", "request_quit", "Quit"),
        ("r", "reload", "Reload"),
        ("s", "switch_channel", "Switch"),
        ("b", "open_browser", "Open Browser"),
        ("c", "copy_login_url", "Copy Login URL"),
        ("p", "add_priority", "Priority"),
        ("x", "add_exclude", "Exclude"),
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
        on_add_priority_game: abc.Callable[[str], None],
        on_add_exclude_game: abc.Callable[[str], None],
        on_remove_priority_game: abc.Callable[[str], None],
        on_remove_exclude_game: abc.Callable[[str], None],
        on_move_priority_game: abc.Callable[[str, int], None],
        on_set_priority_mode: abc.Callable[[str], None],
        on_set_farm_unlinked: abc.Callable[[bool], None],
        on_ready: abc.Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self._on_close = on_close
        self._on_reload = on_reload
        self._login_confirm = login_confirm
        self._on_switch = on_switch
        self._on_save_settings = on_save_settings
        self._on_add_priority_game = on_add_priority_game
        self._on_add_exclude_game = on_add_exclude_game
        self._on_remove_priority_game = on_remove_priority_game
        self._on_remove_exclude_game = on_remove_exclude_game
        self._on_move_priority_game = on_move_priority_game
        self._on_set_priority_mode = on_set_priority_mode
        self._on_set_farm_unlinked = on_set_farm_unlinked
        self._on_ready = on_ready or (lambda: None)
        self._ready_for_refresh = False
        self._syncing_settings = False

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
                                yield Button("open", id="open-browser", compact=True, flat=True)
                                yield Button("copy", id="copy-url", compact=True, flat=True)
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
                with Vertical(id="campaigns"):
                    with Horizontal(classes="filter-strip"):
                        yield Static("show:", id="filter-label")
                        yield Checkbox("not linked", id="filter-not-linked", compact=True)
                        yield Checkbox("upcoming", id="filter-upcoming", compact=True)
                        yield Checkbox("expired", id="filter-expired", compact=True)
                        yield Checkbox("excluded", id="filter-excluded", compact=True)
                        yield Checkbox("finished", id="filter-finished", compact=True)
                    yield DataTable(id="campaigns-table")
            with TabPane("Channels", id="channels-tab"):
                yield DataTable(id="channels-table")
            with TabPane("Settings", id="settings-tab"):
                with Vertical(id="settings"):
                    yield Static("", id="settings-text")
                    with Horizontal(id="settings-grid"):
                        with Vertical(classes="compact-panel grow"):
                            yield Label("Mode")
                            yield Select([], prompt="Priority mode", id="priority-mode-select")
                            yield Checkbox(
                                "farm unlinked drops",
                                id="farm-unlinked",
                                compact=True,
                            )
                            yield Static(
                                "Only for priority-only mode.",
                                id="farm-unlinked-note",
                            )
                            yield Label("Available game")
                            yield Select([], prompt="Select game", id="game-select")
                            with Horizontal(classes="action-row"):
                                yield Button("+ priority", id="add-priority", compact=True, flat=True)
                                yield Button("+ exclude", id="add-exclude", compact=True, flat=True)
                            yield Button("reload", id="reload", compact=True, flat=True)
                        with Vertical(classes="compact-panel grow"):
                            yield Label("Priority")
                            yield DataTable(id="priority-table")
                            with Horizontal(classes="action-row"):
                                yield Button("bump", id="priority-up", compact=True, flat=True)
                                yield Button("demote", id="priority-down", compact=True, flat=True)
                                yield Button("remove", id="remove-priority", compact=True, flat=True)
                        with Vertical(classes="compact-panel grow"):
                            yield Label("Exclude")
                            yield DataTable(id="exclude-table")
                            yield Button("remove", id="remove-exclude", compact=True, flat=True)
            with TabPane("Logs", id="logs-tab"):
                yield Log(id="full-log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Twitch Drops Miner TUI"
        self.sub_title = "tdminer"
        self._setup_tables()
        self._ready_for_refresh = True
        self.refresh_all()
        self.refresh(layout=True)
        self.call_after_refresh(self._on_ready)

    def on_unmount(self) -> None:
        self._ready_for_refresh = False
        self._on_close()

    def _setup_tables(self) -> None:
        campaigns = self.query_one("#campaigns-table", DataTable)
        campaigns.zebra_stripes = True
        campaigns.add_columns("Game", "Campaign", "Status", "Linked", "Progress", "Allowed", "Drops")

        channels = self.query_one("#channels-table", DataTable)
        channels.zebra_stripes = True
        channels.cursor_type = "row"
        channels.add_columns("Channel", "Status", "Game", "Drops", "Viewers", "ACL")

        priority = self.query_one("#priority-table", DataTable)
        priority.cursor_type = "row"
        priority.add_columns("#", "Game")

        exclude = self.query_one("#exclude-table", DataTable)
        exclude.cursor_type = "row"
        exclude.add_columns("Game")

    def _refresh_later(self, callback: abc.Callable[[], None]) -> None:
        if self.is_running and self._ready_for_refresh:
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
        if self.is_running and self._ready_for_refresh:
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
        actions = self._widget("#login-actions", Horizontal)
        if actions is not None:
            actions.display = bool(login.activation_url)

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
        filters = self.state.campaign_filters
        for campaign in self.state.campaigns.values():
            if not self._campaign_visible(campaign):
                continue
            table.add_row(
                campaign.game,
                campaign.name,
                campaign.status,
                "yes" if campaign.linked else "no",
                campaign.percent,
                campaign.allowed_channels,
                "\n".join(campaign.drops),
                key=campaign.id,
            )
        self._syncing_settings = True
        try:
            self._set_checkbox("#filter-not-linked", filters.show_not_linked)
            self._set_checkbox("#filter-upcoming", filters.show_upcoming)
            self._set_checkbox("#filter-expired", filters.show_expired)
            self._set_checkbox("#filter-excluded", filters.show_excluded)
            self._set_checkbox("#filter-finished", filters.show_finished)
        finally:
            self._syncing_settings = False

    def _campaign_visible(self, campaign: Any) -> bool:
        filters = self.state.campaign_filters
        if campaign.required_minutes <= 0:
            return False
        if not filters.show_not_linked and not campaign.linked:
            return False
        if campaign.upcoming and not filters.show_upcoming:
            return False
        if campaign.expired and not filters.show_expired:
            return False
        if campaign.excluded and not filters.show_excluded:
            return False
        if campaign.finished and not filters.show_finished:
            return False
        return campaign.active or campaign.upcoming or campaign.expired

    def refresh_settings(self, *, sync_inputs: bool = False) -> None:
        settings = self._widget("#settings-text", Static)
        if settings is not None:
            settings.update(self.state.settings_text)
        if sync_inputs:
            self._syncing_settings = True
            try:
                self._sync_settings_widgets()
            finally:
                self._syncing_settings = False

    def _sync_settings_widgets(self) -> None:
        mode = self._widget("#priority-mode-select", Select)
        if mode is not None:
            mode.set_options(self.PRIORITY_MODE_OPTIONS)
            mode.value = self.state.priority_mode

        farm_unlinked = self._widget("#farm-unlinked", Checkbox)
        if farm_unlinked is not None:
            farm_unlinked.value = self.state.farm_unlinked
            farm_unlinked.disabled = self.state.priority_mode != "Priority list only"

        game_select = self._widget("#game-select", Select)
        if game_select is not None:
            options = [(game, game) for game in self.state.available_games]
            game_select.set_options(options)

        priority = self._widget("#priority-table", DataTable)
        if priority is not None:
            priority.clear()
            for idx, game in enumerate(self.state.priority, start=1):
                priority.add_row(str(idx), game, key=game)

        exclude = self._widget("#exclude-table", DataTable)
        if exclude is not None:
            exclude.clear()
            for game in self.state.exclude:
                exclude.add_row(game, key=game)

    def _set_checkbox(self, selector: str, value: bool) -> None:
        checkbox = self._widget(selector, Checkbox)
        if checkbox is not None and checkbox.value != value:
            checkbox.value = value

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
        self.exit()
        self._on_close()

    def action_reload(self) -> None:
        self._on_reload()

    def action_switch_channel(self) -> None:
        self._on_switch()

    def action_open_browser(self) -> None:
        self.open_activation_url()

    def action_copy_login_url(self) -> None:
        self.copy_activation_url()

    def action_add_priority(self) -> None:
        game = self._selected_game()
        if game:
            self._on_add_priority_game(game)

    def action_add_exclude(self) -> None:
        game = self._selected_game()
        if game:
            self._on_add_exclude_game(game)

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
        elif button_id == "reload":
            self._on_reload()
        elif button_id == "add-priority":
            self.action_add_priority()
        elif button_id == "add-exclude":
            self.action_add_exclude()
        elif button_id == "remove-priority":
            game = self._selected_table_key("#priority-table")
            if game:
                self._on_remove_priority_game(game)
        elif button_id == "remove-exclude":
            game = self._selected_table_key("#exclude-table")
            if game:
                self._on_remove_exclude_game(game)
        elif button_id == "priority-up":
            game = self._selected_table_key("#priority-table")
            if game:
                self._on_move_priority_game(game, -1)
        elif button_id == "priority-down":
            game = self._selected_table_key("#priority-table")
            if game:
                self._on_move_priority_game(game, 1)

    def on_select_changed(self, event: Select.Changed) -> None:
        if self._syncing_settings:
            return
        if event.select.id == "priority-mode-select" and event.value != Select.NULL:
            mode_name = str(event.value)
            if mode_name != self.state.priority_mode:
                self._on_set_priority_mode(mode_name)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if self._syncing_settings:
            return
        checkbox_id = event.checkbox.id
        if checkbox_id == "farm-unlinked":
            if event.value != self.state.farm_unlinked:
                self._on_set_farm_unlinked(event.value)
            return
        filters = self.state.campaign_filters
        if checkbox_id == "filter-not-linked":
            filters.show_not_linked = event.value
        elif checkbox_id == "filter-upcoming":
            filters.show_upcoming = event.value
        elif checkbox_id == "filter-expired":
            filters.show_expired = event.value
        elif checkbox_id == "filter-excluded":
            filters.show_excluded = event.value
        elif checkbox_id == "filter-finished":
            filters.show_finished = event.value
        else:
            return
        self.refresh_campaigns()

    def _selected_game(self) -> str | None:
        select = self._widget("#game-select", Select)
        if select is None or select.value == Select.NULL:
            return None
        return str(select.value)

    def _selected_table_key(self, selector: str) -> str | None:
        table = self._widget(selector, DataTable)
        if table is None or table.row_count == 0 or table.cursor_row < 0:
            return None
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
        except Exception:
            return None
        if row_key is None:
            return None
        return str(row_key.value)


asyncio_event_setter = abc.Callable[[], None]
