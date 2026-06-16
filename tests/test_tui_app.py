import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from core.constants import PriorityMode
from tui.app import TwitchDropsTUI
from tui.manager import TUIManager
from tui.state import CampaignSnapshot, DropSnapshot, TUIState


class TUIApplicationTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self, state=None, *, on_ready=None, **callbacks):
        return TwitchDropsTUI(
            state or TUIState(),
            on_close=callbacks.get("on_close", lambda: None),
            on_reload=callbacks.get("on_reload", lambda: None),
            login_confirm=callbacks.get("login_confirm", lambda: None),
            on_switch=callbacks.get("on_switch", lambda: None),
            on_save_settings=callbacks.get("on_save_settings", lambda priority, exclude: None),
            on_add_priority_game=callbacks.get("on_add_priority_game", lambda game: None),
            on_add_exclude_game=callbacks.get("on_add_exclude_game", lambda game: None),
            on_remove_priority_game=callbacks.get("on_remove_priority_game", lambda game: None),
            on_remove_exclude_game=callbacks.get("on_remove_exclude_game", lambda game: None),
            on_move_priority_game=callbacks.get("on_move_priority_game", lambda game, offset: None),
            on_set_priority_mode=callbacks.get("on_set_priority_mode", lambda mode: None),
            on_set_farm_unlinked=callbacks.get("on_set_farm_unlinked", lambda enabled: None),
            on_ready=on_ready,
        )

    def test_refresh_later_waits_until_app_is_ready(self):
        app = self.make_app()

        with (
            patch.object(TwitchDropsTUI, "is_running", new_callable=PropertyMock) as is_running,
            patch.object(app, "call_next") as call_next,
        ):
            is_running.return_value = True
            app.refresh_status_later()

        call_next.assert_not_called()

    def test_refresh_login_ignores_missing_widgets_before_mount(self):
        state = TUIState()
        state.login.activation_url = "https://www.twitch.tv/activate"
        state.login.user_code = "ABCD-EFGH"
        app = self.make_app(state)

        app.refresh_login()

    async def test_ready_callback_runs_after_initial_refresh(self):
        ready = []
        app = self.make_app(on_ready=lambda: ready.append("ready"))

        with patch.object(app, "call_after_refresh", wraps=app.call_after_refresh) as after_refresh:
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()

        self.assertTrue(ready)
        self.assertTrue(
            any(call.args and call.args[0] is app._on_ready for call in after_refresh.call_args_list)
        )

    async def test_app_mounts_and_updates_progress_bars(self):
        state = TUIState()
        state.set_drop(
            DropSnapshot(
                campaign="Campaign",
                game="Game",
                rewards="Reward",
                drop_progress=0.4,
                campaign_progress=0.8,
                remaining="00:12:00",
            )
        )
        app = self.make_app(state)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertIn("Reward", str(app.query_one("#drop-title").render()))
            self.assertEqual(app.query_one("#drop-bar").progress, 40)
            self.assertEqual(app.query_one("#campaign-bar").progress, 80)

    async def test_app_mounts_in_narrow_terminal(self):
        app = self.make_app()

        async with app.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#channels-table").is_mounted)
            self.assertTrue(app.query_one("#campaigns-table").is_mounted)

    async def test_login_actions_only_show_for_pending_device_login(self):
        state = TUIState()
        app = self.make_app(state)

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertFalse(app.query_one("#login-actions").display)

            state.login.activation_url = "https://www.twitch.tv/activate"
            state.login.user_code = "ABCD-EFGH"
            app.refresh_login()
            await pilot.pause()

            self.assertTrue(app.query_one("#login-actions").display)

    async def test_campaign_filters_hide_expired_by_default(self):
        state = TUIState()
        state.campaigns["active"] = CampaignSnapshot(
            id="active",
            name="Active Campaign",
            game="Game",
            status="Active",
            linked=True,
            active=True,
            upcoming=False,
            expired=False,
            excluded=False,
            finished=False,
            required_minutes=60,
            progress=0.5,
            drops=("Reward",),
            starts="-",
            ends="-",
            allowed_channels="-",
        )
        state.campaigns["expired"] = CampaignSnapshot(
            id="expired",
            name="Expired Campaign",
            game="Game",
            status="Expired",
            linked=True,
            active=False,
            upcoming=False,
            expired=True,
            excluded=False,
            finished=False,
            required_minutes=60,
            progress=1.0,
            drops=("Reward",),
            starts="-",
            ends="-",
            allowed_channels="-",
        )
        app = self.make_app(state)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            table = app.query_one("#campaigns-table")
            self.assertEqual(table.row_count, 1)

            state.campaign_filters.show_expired = True
            app.refresh_campaigns()
            await pilot.pause()

            self.assertEqual(table.row_count, 2)

    async def test_campaign_table_shows_allowed_offline_channels(self):
        state = TUIState()
        state.campaigns["active"] = CampaignSnapshot(
            id="active",
            name="Single Streamer Campaign",
            game="Game",
            status="Active",
            linked=True,
            active=True,
            upcoming=False,
            expired=False,
            excluded=False,
            finished=False,
            required_minutes=60,
            progress=0.5,
            drops=("Reward",),
            starts="-",
            ends="-",
            allowed_channels="OfflineStreamer",
        )
        app = self.make_app(state)

        async with app.run_test(size=(120, 30)) as pilot:
            await pilot.pause()
            table = app.query_one("#campaigns-table")

            self.assertIn("OfflineStreamer", " ".join(map(str, table.get_row("active"))))

    async def test_campaign_filter_controls_are_visible(self):
        app = self.make_app()

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            self.assertTrue(app.query_one("#filter-label").display)
            self.assertTrue(app.query_one("#filter-not-linked").display)
            self.assertTrue(app.query_one("#filter-upcoming").display)
            self.assertTrue(app.query_one("#filter-expired").display)
            self.assertTrue(app.query_one("#filter-excluded").display)
            self.assertTrue(app.query_one("#filter-finished").display)

    async def test_settings_use_compact_selects_tables_and_checkbox(self):
        state = TUIState()
        state.available_games = ["Game A", "Game B"]
        state.priority = ["Game A"]
        state.exclude = ["Game B"]
        state.farm_unlinked = True
        app = self.make_app(state)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()

            self.assertTrue(app.query_one("#game-select").is_mounted)
            self.assertTrue(app.query_one("#priority-mode-select").is_mounted)
            self.assertTrue(app.query_one("#farm-unlinked").is_mounted)
            self.assertEqual(app.query_one("#priority-table").row_count, 1)
            self.assertEqual(app.query_one("#exclude-table").row_count, 1)

    async def test_settings_refresh_does_not_emit_priority_mode_change(self):
        state = TUIState()
        changes = []
        app = self.make_app(state, on_set_priority_mode=changes.append)

        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.refresh_settings(sync_inputs=True)
            await pilot.pause()

        self.assertEqual(changes, [])


class TUIManagerTests(unittest.IsolatedAsyncioTestCase):
    def test_inventory_snapshot_reads_settings_from_manager(self):
        settings = SimpleNamespace(
            priority=["Game"],
            exclude=set(),
            farm_unlinked=False,
            priority_mode=PriorityMode.PRIORITY_ONLY,
        )
        manager = TUIManager(SimpleNamespace(settings=settings))
        campaign = SimpleNamespace(
            id="campaign",
            name="Campaign",
            game=SimpleNamespace(name="Game"),
            active=True,
            upcoming=False,
            expired=False,
            eligible=True,
            finished=False,
            required_minutes=60,
            progress=0.5,
            drops=[],
            starts_at=datetime.now(timezone.utc),
            ends_at=datetime.now(timezone.utc),
            allowed_channels=[],
        )

        snapshot = manager.inv._snapshot(campaign)

        self.assertEqual(snapshot.game, "Game")
        self.assertFalse(snapshot.excluded)

    async def test_wait_until_ready_has_timeout_fallback(self):
        twitch = SimpleNamespace(
            settings=SimpleNamespace(priority=[], exclude=set(), farm_unlinked=False)
        )
        manager = TUIManager(twitch)
        exits = []
        manager._app = SimpleNamespace(is_running=True, exit=lambda: exits.append("exit"))

        with (
            patch.object(manager, "READY_TIMEOUT", 0.01),
        ):
            await manager.wait_until_ready()

        self.assertTrue(manager._app_ready.is_set())
        self.assertEqual(exits, ["exit"])


if __name__ == "__main__":
    unittest.main()
