import unittest
from unittest.mock import patch

from tui import main as tui_main


class TUIMainTests(unittest.TestCase):
    def test_main_rejects_windows(self):
        with patch("tui.main.sys.platform", "win32"):
            with self.assertRaisesRegex(SystemExit, "only supported on Linux and macOS"):
                tui_main.main(["--version"])


if __name__ == "__main__":
    unittest.main()
