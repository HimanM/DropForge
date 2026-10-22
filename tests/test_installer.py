from pathlib import Path
import http.cookiejar
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
import urllib.request


class InstallerTests(unittest.TestCase):
    def test_web_browser_installation_is_opt_in(self) -> None:
        script = (Path(__file__).parents[1] / "scripts" / "install.sh").read_text(encoding="utf8")
        self.assertIn('if [ "$INSTALL_MODE" = "cli" ] || [ "${TDMINER_INSTALL_BROWSER:-0}" = "1" ]; then', script)
        self.assertIn("Skipping browser installation", script)

    def test_web_bind_policy_defaults_to_localhost(self) -> None:
        script = (Path(__file__).parents[1] / "scripts" / "install.sh").read_text(encoding="utf8")
        self.assertIn('[ -n "$HOST" ] || HOST="127.0.0.1"', script)
        self.assertIn('127.0.0.1|0.0.0.0)', script)
        self.assertIn('printf \'%s\\n\' "$HOST" > "$HOST_FILE"', script)
        self.assertIn('tailscale serve --bg http://127.0.0.1:$PORT', script)
        self.assertIn('ReadWritePaths=$DATA_DIR $APP_DIR/current/lang', script)
        self.assertIn('StandardOutput=journal', script)
        self.assertIn('StandardError=journal', script)
        self.assertIn('Live logs: sudo journalctl -u $SERVICE_NAME.service -f', script)
        self.assertIn('as_root systemctl stop "$SERVICE_NAME.service" || true', script)
        self.assertIn('DropForge Web Access', script)
        self.assertIn("printf '  Admin password  %s\\n'", script)
        self.assertIn("printf '  Recovery code   %s\\n'", script)
        self.assertIn('echo "Twitch retired the password-login endpoint used by this command."', script)
        self.assertIn("import-twitch-token)", script)
        self.assertIn('tdminer_web.py" "\\$1"', script)
        web_main = (Path(__file__).parents[1] / "web" / "main.py").read_text(encoding="utf8")
        self.assertIn('os.environ.get("TDMINER_HOST", "127.0.0.1")', web_main)


@unittest.skipUnless(sys.platform.startswith("linux"), "Isolated Linux installer integration")
class InstallerIntegrationTests(unittest.TestCase):
    def test_fresh_install_real_web_server_update_preservation_and_rollback(self) -> None:
        root = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory(prefix="dropforge-installer-") as directory:
            base = Path(directory)
            bin_dir = base / "bin"
            bin_dir.mkdir()
            archive = base / "source.tar.gz"
            if (root / ".git").exists():
                paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root).decode().split("\0")
            else:
                # Release archives have no git metadata; include only application source/resources.
                folders = ("web", "core", "models", "network", "tui", "gui", "lang", "icons", "tests", "scripts", "docker")
                paths = [str(path.relative_to(root)) for folder in folders for path in (root / folder).rglob("*")
                         if path.is_file() and not {"node_modules", "__pycache__"}.intersection(path.parts)]
                paths += ["tdminer_web.py", "tdminer.py", "main.py", "version.py", "requirements-web.txt", "requirements-tui.txt", "requirements.txt"]
            with tarfile.open(archive, "w:gz") as output:
                for relative in set(paths):
                    source = root / relative
                    if relative and source.is_file():
                        output.add(source, arcname=f"DropForge-test/{relative}")

            def executable(name: str, body: str) -> None:
                path = bin_dir / name
                path.write_text(f"#!{sys.executable}\n" + body)
                path.chmod(0o755)

            executable("id", f"import os,sys\nif sys.argv[1:] == ['-u']: print('1000')\nelse: os.execv({shutil.which('id')!r}, ['id', *sys.argv[1:]])\n")
            executable("sudo", f"""import os,shutil,sys
args=sys.argv[1:]
if args[0]=='cp' and args[-1]=='/etc/systemd/system/tdminer-web.service':
    shutil.copyfile(args[1], {str(base / 'tdminer-web.service')!r})
elif args[0]=='systemctl': os.execv({str(bin_dir / 'systemctl')!r}, args)
else: raise SystemExit('Unexpected elevated operation: '+args[0])
""")
            executable("systemctl", f"""from pathlib import Path
import sys
failure=Path({str(base / 'fail-start')!r})
with Path({str(base / 'systemctl.log')!r}).open('a') as output: output.write(' '.join(sys.argv[1:])+'\\n')
if sys.argv[1]=='restart' and failure.exists():
    failure.unlink()
    raise SystemExit(1)
""")
            executable("curl", f"""import shutil,sys
assert any(value.startswith('https://github.com/') and '/archive/' in value for value in sys.argv), 'Unexpected browser/network download'
shutil.copyfile({str(archive)!r},sys.argv[sys.argv.index('-o')+1])
""")
            executable("python3", f"""import os,sys
args=sys.argv[1:]
if args[:2]==['-m','venv']: args.insert(2,'--system-site-packages')
os.execv({sys.executable!r},[{sys.executable!r},*args])
""")
            env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "TDMINER_MODE": "web",
                   "TDMINER_HOST": "127.0.0.1", "TDMINER_APP_DIR": str(base / "app"),
                   "TDMINER_INSTALL_DIR": str(base / "launchers"), "TDMINER_INSTALL_BROWSER": "0",
                   "TDMINER_ADMIN_PASSWORD": "installer test password", "TDMINER_RECOVERY_CODE": "installer-recovery-test",
                   "PIP_NO_INDEX": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
            def install(success=True):
                result = subprocess.run(["sh", str(root / "scripts/install.sh")], env=env, capture_output=True, text=True, timeout=120)
                self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
                return result.stdout

            install()
            app = base / "app"
            data = app / "data"
            unit = (base / "tdminer-web.service").read_text()
            self.assertIn("StandardOutput=journal", unit)
            self.assertIn(f"ExecStart={app}/current/venv/bin/python {app}/current/tdminer_web.py serve", unit)
            with sqlite3.connect(data / "web-auth.sqlite3") as db:
                self.assertEqual(db.execute("SELECT value FROM settings WHERE name='twitch_login_method'").fetchone()[0], "device")
                original_secrets = db.execute("SELECT * FROM secrets ORDER BY name").fetchall()
            settings = b'{"priority":["Keep Game"],"exclude":["Skip Game"]}'
            token = b'{"access_token":"fake-preserved-session"}'
            (data / "settings.json").write_bytes(settings)
            (data / "web-device-session.json").write_bytes(token)
            (data / "cookies.jar").write_bytes(b"preserved browser cookie fixture")

            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            server = subprocess.Popen([str(app / "current/venv/bin/python"), str(app / "current/tdminer_web.py"),
                "serve", "--host", "127.0.0.1", "--port", str(port), "--no-auto-start"],
                env={**env, "TDMINER_DATA_DIR": str(data)}, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                url = f"http://127.0.0.1:{port}"
                for attempt in range(50):
                    try:
                        with urllib.request.urlopen(url + "/healthz", timeout=1) as response:
                            self.assertTrue(json.load(response)["ok"])
                        break
                    except OSError:
                        if server.poll() is not None:
                            self.fail(server.stderr.read().decode())
                        time.sleep(0.1)
                else:
                    self.fail("Installed web server did not become healthy")
                client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
                request = urllib.request.Request(url + "/api/login", data=json.dumps({"password": env["TDMINER_ADMIN_PASSWORD"]}).encode(), headers={"Content-Type": "application/json", "Origin": url})
                with client.open(request) as response:
                    self.assertTrue(json.load(response)["authenticated"])
                with client.open(url + "/api/state") as response:
                    self.assertEqual(json.load(response)["login_method"], "device")
                with client.open(url) as response:
                    self.assertIn(b"DropForge", response.read())
            finally:
                server.terminate()
                server.communicate(timeout=10)

            self.assertIn("preserved", install())
            current = (app / "current").resolve()
            (base / "fail-start").touch()
            install(success=False)
            self.assertEqual((app / "current").resolve(), current)
            self.assertEqual((data / "settings.json").read_bytes(), settings)
            self.assertEqual((data / "web-device-session.json").read_bytes(), token)
            self.assertEqual((data / "cookies.jar").read_bytes(), b"preserved browser cookie fixture")
            with sqlite3.connect(data / "web-auth.sqlite3") as db:
                self.assertEqual(db.execute("SELECT * FROM secrets ORDER BY name").fetchall(), original_secrets)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0], 1)
            self.assertIn("journalctl", (base / "launchers/tdminer-web").read_text())


if __name__ == "__main__":
    unittest.main()
