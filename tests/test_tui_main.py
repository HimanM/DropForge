import unittest
from unittest.mock import patch

from tui import main as tui_main
from tui.cli import PortableCLIManager
from tui.manager import TUIManager


class TUIMainTests(unittest.TestCase):
    def test_frontend_factory_uses_portable_cli_on_windows_auto(self):
        with patch("tui.main.sys.platform", "win32"):
            self.assertIs(tui_main.frontend_factory("auto"), PortableCLIManager)

    def test_frontend_factory_uses_textual_on_linux_auto(self):
        with patch("tui.main.sys.platform", "linux"):
            self.assertIs(tui_main.frontend_factory("auto"), TUIManager)

    def test_frontend_factory_honors_explicit_frontend(self):
        self.assertIs(tui_main.frontend_factory("cli"), PortableCLIManager)
        self.assertIs(tui_main.frontend_factory("tui"), TUIManager)


if __name__ == "__main__":
    unittest.main()
