# Twitch Drops Miner by HimanM

A personalized fork of Twitch Drops Miner focused on desktop use, Linux/headless use, and a portable terminal interface.

The miner advances Twitch drop progress without playing video. It logs in to Twitch, discovers campaigns, picks eligible channels, switches channels when needed, and claims drop progress in the background.

## Features

- GUI build for normal desktop use.
- Terminal UI through `tdminer`.
- Portable CLI mode for headless Linux, SSH sessions, Termux source installs, and terminals where full TUIs are awkward.
- Twitch device-code login for terminal sessions.
- Saved login through `cookies.jar`.
- Campaign discovery and drop progress tracking.
- Game priority and exclusion lists.
- Automatic channel selection and manual channel switching.
- Optional unlinked-drop farming for the Twitch linked-account display bug.
- Linux/macOS release installer and Termux source installer.

## Desktop Install

Download the latest release from:

https://github.com/HimanM/TwitchDropsMiner/releases

Unzip it, run the app, log in, then use the Settings tab to configure priority/excluded games.

Persistent files such as `cookies.jar`, `settings.json`, `lock.file`, `cache/`, and logs live next to the executable or inside the app bundle, depending on the platform.

## Terminal Install

Linux/macOS:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh
```

The installer downloads the latest matching `tdminer` release asset and installs it to `~/.local/bin` by default.

Custom install location:

```sh
TDMINER_INSTALL_DIR="$HOME/bin" curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh
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

Common commands:

```text
/dashboard
/channels
/channels next
/channels prev
/drops
/drops next
/drops prev
/settings
/logs
/reload
/switch <channel>
/priority add <game>
/priority remove <game>
/exclude add <game>
/exclude remove <game>
/mode priority-only
/mode ending-soonest
/mode low-availability
/farm-unlinked on
/farm-unlinked off
/filter expired on
/filter expired off
/filter finished on
/filter finished off
/quit
```

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

- GUI builds use the original desktop packaging paths.
- `tdminer` release binaries are built with PyInstaller.
- Linux release binaries require compatible glibc Linux systems.
- Termux uses source install instead of release binaries.

## Credits

This fork is maintained by HimanM.

The original Twitch Drops Miner project was created by DevilXD, with contributions from its community.
