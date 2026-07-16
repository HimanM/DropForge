from pathlib import Path
import unittest


class InstallerTests(unittest.TestCase):
    def test_web_bind_policy_defaults_to_localhost(self) -> None:
        script = (Path(__file__).parents[1] / "scripts" / "install.sh").read_text(encoding="utf8")
        self.assertIn('[ -n "$HOST" ] || HOST="127.0.0.1"', script)
        self.assertIn('127.0.0.1|0.0.0.0)', script)
        self.assertIn('printf \'%s\\n\' "$HOST" > "$HOST_FILE"', script)
        self.assertIn('tailscale serve --bg http://127.0.0.1:$PORT', script)
        self.assertIn('ReadWritePaths=$DATA_DIR $APP_DIR/current/lang', script)
        self.assertIn('as_root systemctl stop "$SERVICE_NAME.service" || true', script)
        self.assertIn('DropForge Web Access', script)
        self.assertIn("printf '  Admin password  %s\\n'", script)
        self.assertIn("printf '  Recovery code   %s\\n'", script)
        web_main = (Path(__file__).parents[1] / "web" / "main.py").read_text(encoding="utf8")
        self.assertIn('os.environ.get("TDMINER_HOST", "127.0.0.1")', web_main)


if __name__ == "__main__":
    unittest.main()
