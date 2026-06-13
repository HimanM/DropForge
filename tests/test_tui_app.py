import unittest
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from tui.app import TwitchDropsTUI
from tui.manager import TUIManager
from tui.state import DropSnapshot, TUIState


class TUIApplicationTests(unittest.IsolatedAsyncioTestCase):
    def make_app(self, state=None, *, on_ready=None):
        return TwitchDropsTUI(
            state or TUIState(),
            on_close=lambda: None,
            on_reload=lambda: None,
            login_confirm=lambda: None,
            on_switch=lambda: None,
            on_save_settings=lambda priority, exclude: None,
            on_cycle_priority_mode=lambda: None,
            on_toggle_farm_unlinked=lambda: None,
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

    def test_uses_no_alt_screen_driver_on_windows(self):
        app = self.make_app()

        with patch("tui.app.sys.platform", "win32"):
            driver_class = app.get_driver_class()

        self.assertEqual(driver_class.__name__, "NoAltScreenWindowsDriver")

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


class TUIManagerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_uses_inline_mode_on_windows(self):
        twitch = SimpleNamespace(
            settings=SimpleNamespace(priority=[], exclude=set(), farm_unlinked=False)
        )
        manager = TUIManager(twitch)
        run_kwargs = []

        async def fake_run_async(self, **kwargs):
            run_kwargs.append(kwargs)

        with (
            patch("tui.manager.sys.platform", "win32"),
            patch.object(TwitchDropsTUI, "run_async", fake_run_async),
        ):
            manager.start()
            await manager._app_task

        self.assertEqual(
            run_kwargs,
            [{"inline": True, "inline_no_clear": True}],
        )

    async def test_wait_until_ready_has_timeout_fallback(self):
        twitch = SimpleNamespace(
            settings=SimpleNamespace(priority=[], exclude=set(), farm_unlinked=False)
        )
        manager = TUIManager(twitch)
        manager._app = object()

        with patch.object(manager, "READY_TIMEOUT", 0.01):
            await manager.wait_until_ready()

        self.assertTrue(manager._app_ready.is_set())


if __name__ == "__main__":
    unittest.main()
