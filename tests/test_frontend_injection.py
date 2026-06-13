import unittest
from types import SimpleNamespace

from network.twitch import Twitch


class FrontendInjectionTests(unittest.TestCase):
    def test_twitch_uses_injected_frontend_manager(self):
        created = []

        def factory(twitch):
            manager = SimpleNamespace(twitch=twitch)
            created.append(manager)
            return manager

        settings = SimpleNamespace()
        twitch = Twitch(settings, gui_factory=factory)

        self.assertIs(twitch.gui, created[0])
        self.assertIs(twitch.gui.twitch, twitch)


class FrontendStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_frontend_waits_for_ready_hook(self):
        events = []

        class FakeFrontend:
            def start(self):
                events.append("start")

            async def wait_until_ready(self):
                events.append("ready")

        twitch = Twitch(SimpleNamespace(), gui_factory=lambda _: FakeFrontend())

        await twitch._start_frontend()

        self.assertEqual(events, ["start", "ready"])


if __name__ == "__main__":
    unittest.main()
