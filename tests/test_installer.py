from pathlib import Path
import unittest


class InstallerTests(unittest.TestCase):
    def test_web_bind_policy_defaults_to_localhost(self) -> None:
        script = (Path(__file__).parents[1] / "scripts" / "install.sh").read_text(encoding="utf8")
        self.assertIn('[ -n "$HOST" ] || HOST="127.0.0.1"', script)
        self.assertIn('127.0.0.1|0.0.0.0)', script)
        self.assertIn('printf \'%s\\n\' "$HOST" > "$HOST_FILE"', script)
        self.assertIn('tailscale serve --bg http://127.0.0.1:$PORT', script)
        web_main = (Path(__file__).parents[1] / "web" / "main.py").read_text(encoding="utf8")
        self.assertIn('os.environ.get("TDMINER_HOST", "127.0.0.1")', web_main)


if __name__ == "__main__":
    unittest.main()
