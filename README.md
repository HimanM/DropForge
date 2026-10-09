<p align="center">
  <img src="icons/dropforge.png" alt="DropForge icon" width="152">
</p>

<h1 align="center">DropForge</h1>

<p align="center">
  A desktop, terminal, and self-hosted Twitch drops miner maintained by <a href="https://github.com/HimanM">HimanM</a>.
</p>

<p align="center">
  <a href="https://github.com/HimanM/DropForge/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/HimanM/DropForge?include_prereleases&style=flat-square"></a>
  <a href="https://github.com/HimanM/DropForge/actions/workflows/ci.yml"><img alt="Build status" src="https://github.com/HimanM/DropForge/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://github.com/HimanM/DropForge/actions/workflows/docker.yml"><img alt="Docker image status" src="https://github.com/HimanM/DropForge/actions/workflows/docker.yml/badge.svg"></a>
  <a href="https://github.com/HimanM/DropForge/pkgs/container/dropforge"><img alt="Latest container image" src="https://img.shields.io/badge/GHCR-ghcr.io%2Fhimanm%2Fdropforge-2496ED?style=flat-square&logo=docker&logoColor=white"></a>
</p>

DropForge discovers eligible Twitch campaigns, selects a live channel, advances watch progress without playing video, switches channels when needed, and claims supported rewards. Use the desktop GUI, Linux Web UI, terminal UI, portable CLI, or Docker image.

> [!IMPORTANT]
> Run only one DropForge instance per Twitch account. Running Twitch video or another miner with the same account can make progress reporting unreliable.

## Table of contents

- [Features](#features)
- [Choose an interface](#choose-an-interface)
- [Desktop GUI](#desktop-gui)
- [Linux Web UI](#linux-web-ui)
  - [Install](#install)
  - [Connect Twitch](#connect-twitch)
  - [Remote access](#remote-access)
  - [Manage the service](#manage-the-service)
  - [Update](#update)
- [Docker](#docker)
- [TUI and CLI](#tui-and-cli)
- [Settings](#settings)
- [Data and backups](#data-and-backups)
- [Security](#security)
- [Uninstall](#uninstall)
- [Run from source](#run-from-source)
- [Build and deployment](#build-and-deployment)
- [Credits](#credits)

## Features

- Tracks active, upcoming, completed, excluded, and unlinked campaigns.
- Prioritizes selected games and automatically switches to eligible live channels.
- Supports allowed-channel campaigns and optional ACL bypass for incorrect Twitch channel eligibility data.
- Can farm unlinked drops when Twitch reports the account-link state incorrectly.
- Can farm free watch-time badges while priority work is idle. Subscription badges with `0/0` minutes are skipped.
- Preserves Twitch login, settings, web credentials, and recovery data across updates.
- Sends formatted Discord webhook notifications for selected priority categories.
- Includes campaign, category, reward, progress, and channel artwork in the Web UI.
- Recovers from transient GraphQL, integrity-token, and network failures without routine manual restarts.

## Choose an interface

| Interface | Best for | Platforms | Start here |
| --- | --- | --- | --- |
| Desktop GUI | Regular desktop use | Windows, macOS, Linux | [Download a release](https://github.com/HimanM/DropForge/releases/latest) |
| Web UI | Always-on home server or VPS | Linux, Docker | [One-command install](#install) |
| TUI | Full-screen terminal use | Linux, macOS | `python tdminer.py tui` |
| CLI | SSH, Termux, and simple terminals | Windows, Linux, macOS, Android | `python tdminer.py cli` |
| Docker | Isolated self-hosting | Linux `amd64` and `arm64` | [Compose setup](#docker) |

## Desktop GUI

Download the newest archive from [GitHub Releases](https://github.com/HimanM/DropForge/releases/latest), extract it, and run DropForge.

| Platform | Release asset |
| --- | --- |
| Windows | `DropForge.Windows.zip` |
| macOS | `DropForge.MacOS.zip` |
| Linux AppImage | `DropForge.Linux.AppImage-<arch>.zip` |
| Linux portable GUI | `DropForge.Linux.PyInstaller-<arch>.zip` |

At the Twitch login prompt, choose **Import auth token** and paste the `auth-token` cookie from a signed-in Twitch browser. DropForge saves it in `cookies.jar` beside the portable app data.

## Linux Web UI

### Install

Run the installer as your normal Linux user:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | sh
```

Choose **Web UI** when prompted. The installer:

1. Installs the required system and Python packages.
2. Installs DropForge under `~/.local/share/tdminer`.
3. Creates and starts `tdminer-web.service`.
4. Prints the access URL, admin password, and recovery code in a clearly marked block.
5. Stores persistent data under `~/.local/share/tdminer/data`.

The default address is `http://127.0.0.1:17473`. Save the generated admin password and recovery code before closing the terminal.

To choose the first admin password yourself, use at least 12 characters:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | \
  TDMINER_ADMIN_PASSWORD='replace-with-a-strong-password' sh
```

If `tdminer-web` is not found after installation, add the default launcher directory to your shell path:

```sh
printf '\nexport PATH="$HOME/.local/bin:$PATH"\n' >> ~/.profile
. ~/.profile
```

### Connect Twitch

Twitch retired the password endpoint used by older miners, and its device-code tokens may be rejected by the Drops API. DropForge imports a browser session instead and never asks for your Twitch password.

1. Sign in at [twitch.tv](https://www.twitch.tv/) on a desktop browser.
2. Open the browser developer tools.
3. Open **Application** or **Storage**, then **Cookies**, then `https://www.twitch.tv`.
4. Copy only the value of the cookie named `auth-token`.
5. In DropForge, choose **Import auth token**, or run:

```sh
tdminer-web import-twitch-token
```

Treat the token like a password. The command briefly stops the miner, validates the session, saves it, and restores the service. Copying the same token to another installation is possible, but only one miner should run for that account.

### Remote access

Localhost is the recommended bind address. [Tailscale Serve](https://tailscale.com/kb/1242/tailscale-serve) provides private HTTPS access to devices on your tailnet:

```sh
tailscale serve --bg http://127.0.0.1:17473
```

To expose DropForge directly to the LAN, reinstall or update with `0.0.0.0`:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | \
  TDMINER_HOST=0.0.0.0 sh
```

Then open `http://SERVER_IP:17473`. This is plain HTTP and listens on every reachable interface. Use it only on a trusted network or behind a trusted HTTPS reverse proxy.

To use another port:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | \
  TDMINER_PORT=28461 sh
```

### Manage the service

| Command | Action |
| --- | --- |
| `tdminer-web status` | Show service status |
| `tdminer-web start` | Start the Web UI and miner controller |
| `tdminer-web stop` | Stop the Web UI and mining |
| `tdminer-web restart` | Restart the service |
| `tdminer-web logs` | Follow service logs |
| `tdminer-web reset-password` | Set a new admin password and revoke browser sessions |
| `tdminer-web import-twitch-token` | Replace the saved Twitch session |

Logging out of the website clears only the web browser session. It does not stop the miner or sign the saved Twitch session out.

### Update

Run the same installer command again:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | sh
```

The installer remembers the selected interface and bind address. It stages the new release, keeps persistent data, restarts the service, and restores the previous release if startup fails.

To switch an existing Linux installation between interfaces:

```sh
# Web UI
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | TDMINER_MODE=web sh

# Portable CLI
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | TDMINER_MODE=cli sh
```

## Docker

The latest multi-architecture image is published for `linux/amd64` and `linux/arm64`:

```text
ghcr.io/himanm/dropforge:latest
```

The package and available tags are listed on the [DropForge container page](https://github.com/HimanM/DropForge/pkgs/container/dropforge).

### Docker Compose

```sh
mkdir -p dropforge && cd dropforge
curl -fsSLO https://raw.githubusercontent.com/HimanM/DropForge/main/docker-compose.yml
docker compose up -d
docker compose logs dropforge
```

The Compose file publishes `127.0.0.1:17473`, restarts the container unless stopped, and stores state in the `dropforge-data` volume. The first logs contain the generated admin password and recovery code.

Set the first admin password yourself if needed:

```sh
TDMINER_ADMIN_PASSWORD='replace-with-a-strong-password' docker compose up -d
```

Update the container without losing settings or sessions:

```sh
docker compose pull
docker compose up -d
```

Useful commands:

```sh
docker compose ps
docker compose logs -f dropforge
docker compose restart dropforge
docker compose stop
docker compose down
```

`docker compose down` keeps the named data volume. `docker compose down -v` permanently deletes it.

## TUI and CLI

On Linux, the one-command installer can install the CLI directly:

```sh
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | TDMINER_MODE=cli sh
tdminer --import-token
tdminer
```

The installed Linux launcher uses the portable CLI. For the Textual TUI, run from source or download `DropForge.TUI.<platform>.zip` from [GitHub Releases](https://github.com/HimanM/DropForge/releases/latest):

```sh
python tdminer.py tui
```

Force the portable CLI from source:

```sh
python tdminer.py cli
```

Add verbose file logging when troubleshooting:

```sh
python tdminer.py cli --log -vv
```

The CLI supports slash-command autocomplete. Type `/help` for the complete command list.

| Command | Action |
| --- | --- |
| `/reload` | Refresh inventory and campaigns |
| `/switch <channel>` | Switch to a listed channel |
| `/priority add <game>` | Add a priority game |
| `/priority remove <game>` | Remove a priority game |
| `/exclude add <game>` | Exclude a game |
| `/exclude remove <game>` | Remove an exclusion |
| `/mode <mode>` | Select `priority-only`, `ending-soonest`, or `low-availability` |
| `/farm-unlinked on\|off` | Toggle unlinked-drop farming in priority-only mode |
| `/badges on\|off` | Include badge and emote campaigns in normal farming |
| `/auto-badges on\|off` | Farm free watch-time badges while priority work is idle |
| `/channels`, `/drops`, `/settings`, `/logs` | Change CLI view |
| `/quit` | Exit DropForge |

Termux installs from source because Android does not run glibc Linux binaries:

```sh
pkg install python clang curl tar
curl -fsSL https://raw.githubusercontent.com/HimanM/DropForge/main/scripts/install.sh | sh
tdminer --import-token
tdminer
```

## Settings

- **Priority mode** controls campaign order. **Priority list only** limits farming to selected games.
- **Farm unlinked drops** is available only in priority-list-only mode.
- **Trust allowed channels** follows Twitch campaign ACLs. Disable it only when Twitch shows a valid allowed channel but incorrectly marks it as ineligible.
- **Badge and emote drops** includes those rewards in normal campaign selection.
- **Auto-farm free badges** runs only when priority work is idle and skips subscription badges.
- **Priority and excluded games** are managed in the dedicated Games page or the desktop Settings tab.
- Use **Save and reload** after selection changes so the active inventory is rebuilt immediately.
- Discord notifications are filtered to priority categories to avoid unrelated campaign spam.

Some campaigns require a linked game account. Manage links at [Twitch Drops campaigns](https://www.twitch.tv/drops/campaigns).

## Data and backups

| Installation | Persistent data |
| --- | --- |
| Linux installer | `~/.local/share/tdminer/data` |
| Docker Compose | `dropforge-data` volume mounted at `/data` |
| Portable desktop build | Beside the executable or app bundle |
| Source run | Repository working directory unless `TDMINER_DATA_DIR` is set |

Important files include:

| Path | Purpose |
| --- | --- |
| `cookies.jar` | Twitch session, keep private |
| `cookies.jar.backup` | Last recoverable Twitch session |
| `settings.json` | Miner, priority, webhook, and interface settings |
| `web-auth.sqlite3` | Hashed web credentials and browser sessions |
| `cache/` | Cached campaign and image data |
| `log.txt` | File log when logging is enabled |

Back up the data directory or Docker volume while DropForge is stopped. Updates do not replace these files.

## Security

- Web passwords and recovery codes are salted and hashed with scrypt.
- Web session cookies are opaque and HttpOnly.
- The Twitch `auth-token`, `cookies.jar`, recovery code, and Discord webhook URL are secrets.
- Website logout revokes that browser session but leaves the miner and Twitch session running.
- Changing the admin password revokes all active web browser sessions.
- Prefer localhost with Tailscale Serve or an HTTPS reverse proxy over direct public exposure.
- Never post logs or settings until secrets have been removed.

## Uninstall

Stop and remove a Linux Web UI installation while keeping data for a later reinstall:

```sh
sudo systemctl disable --now tdminer-web.service
sudo rm -f /etc/systemd/system/tdminer-web.service
sudo systemctl daemon-reload
rm -f ~/.local/bin/tdminer-web ~/.local/bin/tdminer
rm -rf ~/.local/share/tdminer/releases ~/.local/share/tdminer/current
rm -f ~/.local/share/tdminer/install-mode ~/.local/share/tdminer/web-host
```

If the installer opened UFW port `17473`, remove the rule:

```sh
sudo ufw delete allow 17473/tcp
```

Delete all settings, web credentials, and the Twitch session only when you no longer need them:

```sh
rm -rf ~/.local/share/tdminer
```

This last command cannot be undone. Adjust the paths if `TDMINER_INSTALL_DIR` or `TDMINER_APP_DIR` was customized.

## Run from source

Python 3.10 or newer is required.

### Linux and macOS

```sh
git clone https://github.com/HimanM/DropForge.git
cd DropForge
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-tui.txt
python tdminer.py --import-token
python tdminer.py tui
```

### Windows PowerShell

```powershell
git clone https://github.com/HimanM/DropForge.git
Set-Location DropForge
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

For the portable Windows CLI, install `requirements-tui.txt` and run `python tdminer.py cli`.

## Build and deployment

GitHub Actions builds the Windows and macOS GUI, Linux GUI and AppImage packages for `x86_64` and `aarch64`, terminal binaries, install script artifact, and the GHCR image. See [DEPLOY.md](DEPLOY.md) for source-build prerequisites and packaging details.

## Credits

DropForge is maintained by [HimanM](https://github.com/HimanM).

The original Twitch Drops Miner was created by [DevilXD](https://github.com/DevilXD/TwitchDropsMiner) with contributions from its community.
