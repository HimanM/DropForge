import unittest
from types import SimpleNamespace

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from core.constants import PriorityMode
from tui.cli import CommandCompleter, PortableCLIManager
from tui.state import CampaignSnapshot, ChannelSnapshot


class SettingsStub:
    def __init__(self):
        self.priority = []
        self.exclude = set()
        self.farm_unlinked = False
        self.priority_mode = PriorityMode.PRIORITY_ONLY
        self.saved = False

    def save(self):
        self.saved = True


class PortableCLITests(unittest.TestCase):
    def make_manager(self):
        twitch = SimpleNamespace(
            settings=SettingsStub(),
            close=lambda: None,
            change_state=lambda state: None,
        )
        return PortableCLIManager(twitch)

    def test_screen_includes_himanm_credit(self):
        manager = self.make_manager()

        text = manager._screen_text()

        self.assertIn("TDMinER by HimanM", text)

    def test_command_completer_includes_common_commands(self):
        self.assertIn("/channels next", PortableCLIManager.COMMANDS)
        self.assertIn("/filter expired on", PortableCLIManager.COMMANDS)
        self.assertIn("/quit", PortableCLIManager.COMMANDS)

    def test_command_completer_triggers_from_slash_prefix(self):
        completer = CommandCompleter(PortableCLIManager.COMMANDS)

        completions = list(
            completer.get_completions(Document("/cha", cursor_position=4), CompleteEvent())
        )

        self.assertTrue(any(completion.text == "/channels" for completion in completions))
        self.assertTrue(any(completion.text == "/channels next" for completion in completions))

    def test_command_completer_ignores_non_command_text(self):
        completer = CommandCompleter(PortableCLIManager.COMMANDS)

        completions = list(
            completer.get_completions(Document("cha", cursor_position=3), CompleteEvent())
        )

        self.assertEqual([], completions)

    def test_command_completer_suggests_available_games_for_priority_add(self):
        candidates = {"/priority add": ["Overwatch", "Sports"]}
        completer = CommandCompleter(
            PortableCLIManager.COMMANDS,
            lambda command: candidates.get(command, []),
        )

        completions = list(
            completer.get_completions(Document("/priority add O", cursor_position=15), CompleteEvent())
        )

        self.assertEqual(["Overwatch"], [completion.text for completion in completions])

    def test_command_completer_inserts_space_before_argument_after_exact_command(self):
        candidates = {"/farm-unlinked": ["on", "off"]}
        completer = CommandCompleter(
            PortableCLIManager.COMMANDS,
            lambda command: candidates.get(command, []),
        )

        completions = list(
            completer.get_completions(Document("/farm-unlinked", cursor_position=14), CompleteEvent())
        )

        self.assertIn(" on", [completion.text for completion in completions])
        self.assertIn(" off", [completion.text for completion in completions])

    def test_dynamic_completions_use_manager_state(self):
        manager = self.make_manager()
        manager.state.available_games = ["Overwatch", "Sports"]
        manager.state.priority = ["Sports"]
        manager.state.channels["1"] = ChannelSnapshot(
            iid="1",
            name="channel-one",
            status="ONLINE",
            game="Overwatch",
            viewers="10",
            drops=True,
            acl_based=False,
        )

        self.assertEqual(["Overwatch"], manager._completion_candidates("/priority add"))
        self.assertEqual(["channel-one"], manager._completion_candidates("/switch"))

    def test_switch_command_accepts_channel_name(self):
        manager = self.make_manager()
        manager.state.channels["1"] = ChannelSnapshot(
            iid="1",
            name="channel-one",
            status="ONLINE",
            game="Overwatch",
            viewers="10",
            drops=True,
            acl_based=False,
        )

        manager._handle_command("/switch channel-one")

        self.assertEqual("1", manager.selected_channel_id())

    def test_print_logs_without_textual_app(self):
        manager = self.make_manager()

        manager.print("hello")

        self.assertTrue(any("hello" in line for line in manager.state.logs))

    def test_stop_ignores_prompt_toolkit_app_that_is_not_running(self):
        manager = self.make_manager()
        manager._pt_app = SimpleNamespace(
            future=None,
            exit=lambda: self.fail("exit should not be called for a stopped app"),
        )

        manager.stop()

    def test_stop_ignores_prompt_toolkit_app_that_already_exited(self):
        manager = self.make_manager()
        manager._pt_app = SimpleNamespace(
            future=SimpleNamespace(done=lambda: True),
            exit=lambda: self.fail("exit should not be called for a completed app"),
        )

        manager.stop()

    def test_channels_view_is_capped_and_scrollable(self):
        manager = self.make_manager()
        for index in range(15):
            manager.state.channels[str(index)] = ChannelSnapshot(
                iid=str(index),
                name=f"channel-{index}",
                status="ONLINE",
                game="Game",
                viewers=str(index),
                drops=True,
                acl_based=False,
                watching=index == 0,
            )

        first_page = "\n".join(manager._channels_lines(120))
        manager._scroll_channels("next")
        second_page = "\n".join(manager._channels_lines(120))

        self.assertIn("channel-0", first_page)
        self.assertNotIn("channel-10", first_page)
        self.assertIn("channel-10", second_page)
        self.assertIn("/channels next", first_page)

    def test_channels_view_removes_columns_in_narrow_terminals(self):
        manager = self.make_manager()
        manager.state.channels["1"] = ChannelSnapshot(
            iid="1",
            name="channel-1",
            status="ONLINE",
            game="Very Long Game",
            viewers="999",
            drops=True,
            acl_based=True,
            watching=False,
        )

        text = "\n".join(manager._channels_lines(56))

        self.assertIn("channel-1", text)
        self.assertIn("drop", text)
        self.assertNotIn("viewers", text)
        self.assertNotIn("acl", text)

    def test_drops_view_is_capped_scrollable_and_filterable(self):
        manager = self.make_manager()
        for index in range(12):
            manager.state.campaigns[str(index)] = CampaignSnapshot(
                id=str(index),
                name=f"Campaign {index}",
                game=f"Game {index}",
                status="Active",
                linked=True,
                active=True,
                upcoming=False,
                expired=False,
                excluded=False,
                finished=False,
                required_minutes=60,
                progress=0.25,
                drops=("Reward",),
                starts="-",
                ends="-",
                allowed_channels="-",
            )
        manager.state.campaigns["expired"] = CampaignSnapshot(
            id="expired",
            name="Expired Campaign",
            game="Expired Game",
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

        first_page = "\n".join(manager._drops_lines(120))
        manager._scroll_campaigns("next")
        second_page = "\n".join(manager._drops_lines(120))
        manager._handle_filter("expired on")
        manager._scroll_campaigns("next")
        filtered = "\n".join(manager._drops_lines(120))

        self.assertIn("Campaign 0", first_page)
        self.assertNotIn("Campaign 8", first_page)
        self.assertIn("Campaign 8", second_page)
        self.assertIn("Expired Campaign", filtered)
        self.assertIn("expired=on", filtered)

    def test_drops_view_removes_columns_in_narrow_terminals(self):
        manager = self.make_manager()
        manager.state.campaigns["1"] = CampaignSnapshot(
            id="1",
            name="Long Campaign",
            game="Game",
            status="Active",
            linked=True,
            active=True,
            upcoming=False,
            expired=False,
            excluded=False,
            finished=False,
            required_minutes=60,
            progress=0.25,
            drops=("Reward",),
            starts="-",
            ends="-",
            allowed_channels="-",
        )

        text = "\n".join(manager._drops_lines(56))

        self.assertIn("Game", text)
        self.assertIn("progress", text)
        self.assertNotIn(" yes ", text)
        self.assertNotIn("Long Campaign", text)


if __name__ == "__main__":
    unittest.main()
