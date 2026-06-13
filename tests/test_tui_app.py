import unittest

from tui.app import TwitchDropsTUI
from tui.state import DropSnapshot, TUIState


class TUIApplicationTests(unittest.IsolatedAsyncioTestCase):
    def test_refresh_login_ignores_missing_widgets_before_mount(self):
        state = TUIState()
        state.login.activation_url = "https://www.twitch.tv/activate"
        state.login.user_code = "ABCD-EFGH"
        app = TwitchDropsTUI(
            state,
            on_close=lambda: None,
            on_reload=lambda: None,
            login_confirm=lambda: None,
            on_switch=lambda: None,
            on_save_settings=lambda priority, exclude: None,
            on_cycle_priority_mode=lambda: None,
            on_toggle_farm_unlinked=lambda: None,
        )

        app.refresh_login()

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
        app = TwitchDropsTUI(
            state,
            on_close=lambda: None,
            on_reload=lambda: None,
            login_confirm=lambda: None,
            on_switch=lambda: None,
            on_save_settings=lambda priority, exclude: None,
            on_cycle_priority_mode=lambda: None,
            on_toggle_farm_unlinked=lambda: None,
        )

        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            self.assertIn("Reward", str(app.query_one("#drop-title").render()))
            self.assertEqual(app.query_one("#drop-bar").progress, 40)
            self.assertEqual(app.query_one("#campaign-bar").progress, 80)

    async def test_app_mounts_in_narrow_terminal(self):
        app = TwitchDropsTUI(
            TUIState(),
            on_close=lambda: None,
            on_reload=lambda: None,
            login_confirm=lambda: None,
            on_switch=lambda: None,
            on_save_settings=lambda priority, exclude: None,
            on_cycle_priority_mode=lambda: None,
            on_toggle_farm_unlinked=lambda: None,
        )

        async with app.run_test(size=(60, 18)) as pilot:
            await pilot.pause()
            self.assertTrue(app.query_one("#channels-table").is_mounted)
            self.assertTrue(app.query_one("#campaigns-table").is_mounted)


if __name__ == "__main__":
    unittest.main()
