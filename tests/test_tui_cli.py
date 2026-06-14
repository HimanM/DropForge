import unittest
from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from core.constants import PriorityMode
from tui.cli import PortableCLIManager
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

    def render_text(self, renderable) -> str:
        console = Console(record=True, width=120, color_system=None, file=StringIO())
        console.print(renderable)
        return console.export_text()

    def test_header_includes_himanm_credit(self):
        manager = self.make_manager()

        text = self.render_text(manager._header())

        self.assertIn("TDMinER by HimanM", text)

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

        first_page = self.render_text(manager._channels_view())
        manager._scroll_channels("next")
        second_page = self.render_text(manager._channels_view())

        self.assertIn("channel-0", first_page)
        self.assertNotIn("channel-10", first_page)
        self.assertIn("channel-10", second_page)
        self.assertIn("/channels next", first_page)

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

        first_page = self.render_text(manager._drops_view())
        manager._scroll_campaigns("next")
        second_page = self.render_text(manager._drops_view())
        manager._handle_filter("expired on")
        manager._scroll_campaigns("next")
        filtered = self.render_text(manager._drops_view())

        self.assertIn("Campaign 0", first_page)
        self.assertNotIn("Campaign 8", first_page)
        self.assertIn("Campaign 8", second_page)
        self.assertIn("Expired Campaign", filtered)
        self.assertIn("/drops next", first_page)


if __name__ == "__main__":
    unittest.main()
