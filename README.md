<p align="center">
  <img src="icons/dropforge.png" alt="DropForge icon" width="160">
</p>

# DropForge

DropForge is HimanM's desktop, server, and terminal Twitch drops miner.

The miner advances Twitch drop progress without playing video. It logs in to Twitch, discovers campaigns, picks eligible channels, switches channels when needed, and claims drop progress in the background.

## Features

- DropForge desktop GUI for normal desktop use.
- DropForge Web UI for authenticated, image-rich Linux server control from desktop or mobile browsers.
- DropForge terminal UI through `tdminer`.
- Portable CLI mode for headless Linux, SSH sessions, Termux source installs, and terminals where full TUIs are awkward.
- Twitch device-code login for terminal sessions.
- Secure import of an existing Twitch browser `auth-token`.
- Saved login through `cookies.jar`.
- Campaign discovery and drop progress tracking.
- Game priority and exclusion lists.
- Automatic channel selection and manual channel switching.
- Optional unlinked-drop farming for the Twitch linked-account display bug.
- Optional idle farming for free watch-time badges; subscription (`0/0`) badges are skipped.
- One-command Linux Web UI or CLI installer with in-place updates and persistent data.

## Desktop Install

Download the latest release from:

https://github.com/HimanM/TwitchDropsMiner/releases

Unzip it, run the app, log in, then use the Settings tab to configure priority/excluded games.

Persistent files such as `cookies.jar`, `settings.json`, `lock.file`, `cache/`, and logs live next to the executable or inside the app bundle, depending on the platform.

## Linux Server Install

Run the installer and choose the Web UI or CLI when prompted:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh
```

The first Web UI install prints a generated admin password and recovery code, then asks whether to bind to localhost or `0.0.0.0`. Localhost is recommended and selected by default. Re-running the same command updates the selected interface while preserving the bind choice, Twitch cookie jar, settings, admin credentials, recovery data, and browser sessions under `~/.local/share/tdminer/data`.

For private remote access while keeping the app on localhost, install Tailscale and run:

```sh
tailscale serve --bg http://127.0.0.1:17473
```

To expose the port directly on every network interface instead:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | TDMINER_HOST=0.0.0.0 sh
```

The installer remembers the selected interface. For unattended installs or to switch later:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | TDMINER_MODE=web sh
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | TDMINER_MODE=cli sh
```

Web service commands:

```sh
tdminer-web status
tdminer-web start
tdminer-web stop
tdminer-web restart
tdminer-web logs
tdminer-web reset-password
tdminer-web login-twitch
tdminer-web import-twitch-token
```

Stopping `tdminer-web` stops both the Web UI and mining. Starting it again resumes the saved installation and Twitch session.

### Connect a Twitch account

For a Linux Web UI installation, the recommended login is:

```sh
tdminer-web login-twitch
```

This stops the DropForge service temporarily, asks for the Twitch username, password, and any required 2FA or email code in the terminal, and restarts the service afterward. Credentials are sent directly to Twitch and are never saved; only the resulting Android session token is stored. This client avoids Twitch's browser-integrity requirement on headless servers.

The Web UI and Windows GUI offer **Log in with Twitch** and **Import auth token**. To import a browser session, open your browser's developer tools, find Cookies for `https://www.twitch.tv`, and copy only the value named `auth-token`. Treat it like a password.

For Linux CLI/server installs, use `tdminer --import-token` or `tdminer-web import-twitch-token`. DropForge validates both the token and full drops-campaign access before replacing the saved token, and keeps a `cookies.jar.backup` copy. Browser tokens require Twitch's short-lived integrity proof, so desktop builds use an installed Chrome, Edge, or Brave and the Linux installer provisions Chromium with Xvfb for automatic hourly refresh. Set `TDMINER_BROWSER` only when the browser executable is in a custom location.

One token can be copied to multiple installations, but only run one miner for that Twitch account at a time. Logging out of Twitch or revoking the session invalidates every copy.

To uninstall the default Web UI installation while keeping `~/.local/share/tdminer/data` for a later reinstall:

```sh
sudo systemctl disable --now tdminer-web.service
sudo rm -f /etc/systemd/system/tdminer-web.service
sudo systemctl daemon-reload
rm -f ~/.local/bin/tdminer-web
rm -rf ~/.local/share/tdminer/releases ~/.local/share/tdminer/current
rm -f ~/.local/share/tdminer/install-mode ~/.local/share/tdminer/web-host
```

If the installer opened port `17473` in UFW, remove that rule too:

```sh
sudo ufw delete allow 17473/tcp
```

For a complete uninstall, including the Twitch cookie jar, settings, web password, recovery data, and browser sessions, also run:

```sh
rm -rf ~/.local/share/tdminer
```

The last command permanently deletes all DropForge data. If `TDMINER_INSTALL_DIR` or `TDMINER_APP_DIR` was customized during installation, use those paths instead.

Passwords and recovery codes are salted and hashed with scrypt. Session cookies are opaque, HttpOnly, and cleared on website logout. Website logout does not stop mining or clear the Twitch cookie jar. Binding to `0.0.0.0` uses HTTP, so use it only on a trusted network; localhost plus Tailscale Serve is recommended for private HTTPS remote access.

macOS terminal install uses the same command and installs the latest release asset.

Custom install location:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | TDMINER_INSTALL_DIR="$HOME/bin" sh
```

Termux:

```sh
pkg install python clang curl tar
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh
```

Native Termux cannot run the Linux release binary because Android does not use glibc Linux executables. On Termux, the installer downloads the source, creates a Python virtual environment in `~/.local/share/tdminer`, installs dependencies, and creates a `tdminer` launcher in `$PREFIX/bin`.

## Running

Automatic terminal frontend:

```sh
tdminer
```

Textual TUI:

```sh
tdminer tui
```

Portable CLI:

```sh
tdminer cli
```

Verbose logs:

```sh
tdminer cli --log -vv
```

The terminal login uses Twitch device activation. If login is needed, `tdminer` shows a URL and code. You can open the URL from the UI, copy it, or type it manually on another device for headless systems.

## CLI Commands

The portable CLI has a boxed command input with slash-command autocomplete.

Type `/` to list commands. Type `/priority add `, `/exclude add `, or `/switch ` to autocomplete available games and channels.

Type `/help` in the CLI to view all commands grouped by category with descriptions.

### Navigation

| Command | Description |
|---------|-------------|
| `/dashboard` | Switch to the dashboard view (default) |
| `/channels` | Switch to the channels list view |
| `/channels next` | Page forward in the channels list |
| `/channels prev` | Page backward in the channels list |
| `/drops` | Switch to the drops/campaigns view |
| `/drops next` | Page forward in the drops list |
| `/drops prev` | Page backward in the drops list |
| `/settings` | Switch to the settings view |
| `/logs` | Switch to the logs view |
| `/help` | Show the help page (use `/help <topic>` for details) |

### Control

| Command | Description |
|---------|-------------|
| `/reload` | Reload inventory and campaign data from Twitch |
| `/switch <channel>` | Switch to a specific channel by name or ID |
| `/priority add <game>` | Add a game to the priority list |
| `/priority remove <game>` | Remove a game from the priority list |
| `/priority bump <game>` | Move a game up in the priority list |
| `/priority demote <game>` | Move a game down in the priority list |
| `/exclude add <game>` | Add a game to the exclude list |
| `/exclude remove <game>` | Remove a game from the exclude list |
| `/mode <mode>` | Set priority mode: `priority-only`, `ending-soonest`, `low-availability` |
| `/filter <name> <on\|off>` | Toggle filters: `not-linked`, `upcoming`, `expired`, `excluded`, `finished` |
| `/farm-unlinked on\|off` | Enable/disable farming unlinked drops (priority-only mode) |
| `/badges on\|off` | Include badge and emote campaigns in normal farming |
| `/auto-badges on\|off` | Farm free watch-time badges only when priority work is idle |

### System

| Command | Description |
|---------|-------------|
| `/open` | Open the Twitch login URL in a browser (when login is pending) |
| `/copy` | Show the Twitch login URL (when login is pending) |
| `/detach` | Detach from current tmux session (keeps miner running) |
| `/quit` | Exit the application |

## TUI Shortcuts

```text
q  quit
r  reload inventory/campaign data
s  switch to the selected channel
b  open Twitch login URL when login is pending
c  copy Twitch login URL when login is pending
```

## Settings Notes

- Priority mode controls how games are selected.
- Farm unlinked drops only works in priority-only mode.
- Auto-farm free badges is off by default. Priority work always wins, and completed badges are remembered across updates.
- Priority and exclude changes require an inventory reload before they affect channel selection.
- Link Twitch campaigns to game accounts on https://www.twitch.tv/drops/campaigns when required by the campaign.

## Security Notes

- `cookies.jar` stores your Twitch session. Keep it private.
- Twitch may send a new-login email after device login. That is expected.
- Avoid watching Twitch in a browser with the same account while the miner is active, because Twitch may report progress inconsistently.

## Source Run

Python 3.10+ is required.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-tui.txt
python tdminer.py cli
```

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-tui.txt
python tdminer.py cli
```

## Build Notes

- Desktop GUI builds are packaged as DropForge applications.
- `tdminer` release binaries are built with PyInstaller.
- Linux release binaries require compatible glibc Linux systems.
- Termux uses source install instead of release binaries.
- For full build and deployment instructions across all platforms, see [DEPLOY.md](DEPLOY.md).

## Credits

This fork is maintained by HimanM.

The original Twitch Drops Miner project was created by DevilXD, with contributions from its community.
