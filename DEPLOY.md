# Deployment Guide

Complete guide to running and building Twitch Drops Miner across every platform and frontend.

## Table of Contents

- [Frontend Overview](#frontend-overview)
- [Running from Source](#running-from-source)
  - [Windows](#windows-source)
  - [Linux](#linux-source)
  - [macOS](#macos-source)
  - [Termux / Android](#termux--android-source)
- [Pre-built Releases](#pre-built-releases)
- [Building from Source](#building-from-source)
  - [Building the GUI](#building-the-gui)
  - [Building the TUI / CLI Binary](#building-the-tui--cli-binary)
  - [Building the Linux AppImage](#building-the-linux-appimage)
- [Platform Reference Matrix](#platform-reference-matrix)
- [Persistent Data Locations](#persistent-data-locations)
- [Troubleshooting](#troubleshooting)

---

## Frontend Overview

The project has three frontends:

| Frontend | Entry Point | Dependencies | Platforms |
|----------|------------|--------------|-----------|
| **GUI** | `main.py` | `requirements.txt` (tkinter, pystray, Pillow) | Windows, Linux, macOS |
| **TUI** | `tdminer.py` (with `tui` arg) | `requirements-tui.txt` (textual, rich, prompt_toolkit) | Linux, macOS |
| **CLI** | `tdminer.py` (with `cli` arg) | `requirements-tui.txt` (rich, prompt_toolkit) | Windows, Linux, macOS, Termux |

- **GUI** — Full graphical interface with tkinter, system tray, and progress bars.
- **TUI** — Rich terminal UI using Textual (full-screen, mouse support, tabs). Only on Linux/macOS.
- **CLI** — Portable prompt_toolkit-based terminal with Rich styling, slash-command autocomplete. Works everywhere including Windows and Termux.

The `tdminer` entry point auto-selects: on Windows it defaults to CLI, on Linux/macOS it defaults to TUI. You can force either with `tdminer cli` or `tdminer tui`.

---

## Running from Source

**Requires:** Python 3.10+

### Windows Source

#### GUI (from source)

```powershell
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Or use the provided batch scripts:

```cmd
setup_env.bat
run_dev.bat
```

#### TUI / CLI (from source)

```powershell
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-tui.txt

# Auto-select (defaults to CLI on Windows)
python tdminer.py

# Force CLI
python tdminer.py cli

# Force TUI (not supported on Windows)
python tdminer.py tui
```

**Note:** The Textual TUI (`tui` mode) is not supported on Windows. Use `cli` mode instead.

### Linux Source

#### GUI (from source)

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

# Install system dependencies (Debian/Ubuntu)
sudo apt install python3-tk gir1.2-ayatanaappindicator3-0.1

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

For Fedora/RHEL:

```bash
sudo dnf install python3-tkinter python3-gobject ayatana-appindicator3-gtk3
```

For Arch:

```bash
sudo pacman -S tk libayatana-appindicator
```

#### TUI / CLI (from source)

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-tui.txt

# Auto-select (defaults to TUI on Linux)
python tdminer.py

# Force TUI
python tdminer.py tui

# Force CLI
python tdminer.py cli
```

### macOS Source

#### GUI (from source)

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

#### TUI / CLI (from source)

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-tui.txt

# Auto-select (defaults to TUI on macOS)
python tdminer.py

# Force TUI
python tdminer.py tui

# Force CLI
python tdminer.py cli
```

### Termux / Android Source

Termux cannot run pre-built Linux binaries because Android uses Bionic libc, not glibc. You must install from source.

#### CLI (only supported frontend on Termux)

```bash
# Install prerequisites
pkg install python clang curl tar

# One-line install (recommended)
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh

# Or manual install
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-tui.txt
python tdminer.py cli
```

The install script creates a `tdminer` launcher in `$PREFIX/bin` (usually `/data/data/com.termux/files/usr/bin`). After installation, just run:

```bash
tdminer
```

**Termux tips:**

- Use `tmux` or `screen` to keep sessions alive in the background.
- The CLI frontend is designed for Termux and works well with its terminal capabilities.
- Data files (cookies, settings, cache) are stored in `~/.local/share/tdminer/data/`.

---

## Pre-built Releases

Download from: https://github.com/HimanM/TwitchDropsMiner/releases

### Available Release Assets

| Asset | Platform | Frontend | Format |
|-------|----------|----------|--------|
| `Twitch.Drops.Miner.Windows.zip` | Windows x86_64 | GUI | Single .exe |
| `Twitch.Drops.Miner.MacOS.zip` | macOS universal | GUI | .app bundle |
| `Twitch.Drops.Miner.Linux.AppImage-x86_64.zip` | Linux x86_64 | GUI | AppImage |
| `Twitch.Drops.Miner.Linux.AppImage-aarch64.zip` | Linux ARM64 | GUI | AppImage |
| `Twitch.Drops.Miner.Linux.PyInstaller-x86_64.zip` | Linux x86_64 | GUI | Single binary |
| `Twitch.Drops.Miner.Linux.PyInstaller-aarch64.zip` | Linux ARM64 | GUI | Single binary |
| `Twitch.Drops.Miner.TUI.Linux-x86_64.zip` | Linux x86_64 | TUI/CLI | Single binary |
| `Twitch.Drops.Miner.TUI.Linux-aarch64.zip` | Linux ARM64 | TUI/CLI | Single binary |
| `Twitch.Drops.Miner.TUI.MacOS.zip` | macOS | TUI/CLI | Single binary |

### Quick Install (Linux/macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh
```

Custom install directory:

```bash
TDMINER_INSTALL_DIR="$HOME/bin" curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh
```

After installation:

```bash
tdminer           # auto-select frontend
tdminer tui       # Textual TUI (Linux/macOS)
tdminer cli       # portable CLI (everywhere)
```

### Quick Install (Termux)

```bash
pkg install python clang curl tar
curl -fsSL https://raw.githubusercontent.com/HimanM/TwitchDropsMiner/main/scripts/install.sh | sh
tdminer
```

---

## Building from Source

### Prerequisites

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.10+ | Runtime | https://python.org |
| pip | Package manager | Included with Python |
| PyInstaller | Binary packaging | `pip install pyinstaller` |
| git | Source checkout | https://git-scm.com |
| 7z (Windows) | Release packaging | Optional, for `pack.bat` |

### Building the GUI

The GUI build packages `main.py` with tkinter, pystray, and Pillow into a standalone executable.

#### Windows GUI Build

```powershell
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

# Set up environment (installs requirements.txt)
setup_env.bat

# Build
build.bat

# Or manually:
py -m venv build-env
.\build-env\Scripts\Activate.ps1
pip install -r requirements.txt pyinstaller
pyinstaller build.spec

# Package the release
pack.bat
```

Output: `dist/Twitch Drops Miner (by HimanM).exe`

The `build.bat` script:
1. Creates/uses the `env/` virtual environment
2. Installs PyInstaller if missing
3. Runs `pyinstaller build.spec`
4. Output goes to `dist/`

#### Linux GUI Build (PyInstaller)

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

# Install system dependencies (Debian/Ubuntu)
sudo apt install python3-tk gir1.2-ayatanaappindicator3-0.1 \
    libgirepository1.0-dev libayatana-appindicator3-1

# Set up environment
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt pyinstaller

# On headless systems, use xvfb for the build
xvfb-run --auto-servernum pyinstaller build.spec

# If libXft is old (< 2.3.5), build a newer version first:
mkdir -p /tmp/libXft && cd /tmp/libXft
curl -fL https://xorg.freedesktop.org/releases/individual/lib/libXft-2.3.9.tar.xz -o libXft.tar.xz
tar xvf libXft.tar.xz && cd libXft-*
./configure --prefix=/tmp/libXft --disable-static
make -j$(nproc) && make install-strip
cd -

LD_LIBRARY_PATH=/tmp/libXft/lib xvfb-run --auto-servernum pyinstaller build.spec
```

Output: `dist/Twitch Drops Miner (by HimanM)` (one-dir) or single executable

#### Linux GUI Build (AppImage)

```bash
# Install appimage-builder
pip install git+https://github.com/AppImageCrafters/appimage-builder.git@e995e8ed

# Install system dependencies
sudo apt install gir1.2-ayatanaappindicator3-0.1 libayatana-appindicator3-1

# Build
ARCH=x86_64 APP_VERSION=1.0.0 PYTHON_VERSION=3.10 \
    appimage-builder --recipe appimage/AppImageBuilder.yml
```

Output: `Twitch.Drops.Miner-x86_64.AppImage`

The AppImage bundles Python, tkinter, and all dependencies. It runs on most Linux distributions without installation.

#### macOS GUI Build

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

python3 -m venv env
source env/bin/activate
pip install -r requirements.txt pyinstaller

pyinstaller build.spec --noconfirm
```

Output: `dist/Twitch Drops Miner (by HimanM).app`

### Building the TUI / CLI Binary

The TUI build packages `tdminer.py` with textual, rich, and prompt_toolkit into a single terminal binary.

#### Linux TUI Build

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

python3 -m venv env
source env/bin/activate
pip install -r requirements-tui.txt pyinstaller

pyinstaller build_tui.spec --noconfirm
```

Output: `dist/tdminer`

The binary works on Linux systems with compatible glibc. No Python installation needed on the target machine.

#### macOS TUI Build

```bash
git clone https://github.com/HimanM/TwitchDropsMiner.git
cd TwitchDropsMiner

python3 -m venv env
source env/bin/activate
pip install -r requirements-tui.txt pyinstaller

pyinstaller build_tui.spec --noconfirm
```

Output: `dist/tdminer`

#### Windows TUI Build

The TUI build is not officially supported on Windows via PyInstaller, but the CLI mode runs directly from source:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-tui.txt
python tdminer.py cli
```

#### Termux Build

Termux cannot use PyInstaller to create native binaries. Use the source install method described in [Termux / Android Source](#termux--android-source).

### CI / GitHub Actions

The project includes a GitHub Actions workflow (`.github/workflows/ci.yml`) that automatically builds all targets on push to `main`:

- **validate** — Runs TUI tests and compiles Python modules
- **windows** — Builds GUI exe for Windows
- **macos** — Builds GUI .app for macOS
- **macos-tui** — Builds TUI binary for macOS
- **linux-tui** — Builds TUI binary for Linux (x86_64 + aarch64)
- **linux-pyinstaller** — Builds GUI binary for Linux (x86_64 + aarch64)
- **linux-appimage** — Builds GUI AppImage for Linux (x86_64 + aarch64)
- **update_releases_page** — Uploads all artifacts to GitHub Releases

To trigger a build manually, go to Actions > Build > Run workflow.

---

## Platform Reference Matrix

### Frontend Availability

| Platform | GUI | TUI | CLI |
|----------|-----|-----|-----|
| Windows 10/11 | Yes | No | Yes |
| Ubuntu/Debian | Yes | Yes | Yes |
| Fedora/RHEL | Yes | Yes | Yes |
| Arch Linux | Yes | Yes | Yes |
| macOS | Yes | Yes | Yes |
| Termux (Android) | No | No | Yes |
| Docker/headless | No | No | Yes |
| SSH sessions | No | No | Yes |

### Build Method by Platform

| Platform | GUI Build | TUI Build |
|----------|-----------|-----------|
| Windows | PyInstaller (`build.spec`) | Source only |
| Linux x86_64 | PyInstaller or AppImage | PyInstaller (`build_tui.spec`) |
| Linux aarch64 | PyInstaller or AppImage | PyInstaller (`build_tui.spec`) |
| macOS | PyInstaller (`build.spec`) | PyInstaller (`build_tui.spec`) |
| Termux | Not available | Source install |

### System Dependencies

| Platform | GUI Dependencies | TUI/CLI Dependencies |
|----------|-----------------|---------------------|
| Windows | None (bundled) | None (bundled) |
| Ubuntu/Debian | `python3-tk`, `gir1.2-ayatanaappindicator3-0.1` | `python3` |
| Fedora | `python3-tkinter`, `python3-gobject`, `ayatana-appindicator3-gtk3` | `python3` |
| Arch | `tk`, `libayatana-appindicator` | `python` |
| macOS | None (bundled in .app) | None |
| Termux | Not available | `python`, `clang`, `curl`, `tar` |

---

## Persistent Data Locations

Data files are stored next to the executable by default, or in a dedicated data directory when using the installer.

| File | Purpose |
|------|---------|
| `cookies.jar` | Twitch session cookies (keep private) |
| `settings.json` | User settings (priority, exclude, mode) |
| `cache/` | Cached images and API responses |
| `lock.file` | Prevents multiple instances |
| `logs/` | Log files (when `--log` is used) |

### Installer Data Directory

When using the install script, data is stored in:

- **Linux/macOS:** `~/.local/share/tdminer/data/`
- **Termux:** `~/.local/share/tdminer/data/`

The `TDMINER_DATA_DIR` environment variable can override this.

### Portable Run

When running from source or from a built executable, data files are stored in the current working directory (next to the executable).

---

## Troubleshooting

### "No python executable found"

Ensure Python 3.10+ is installed and in your PATH:

```bash
python3 --version  # Should show 3.10+
```

### "Failed to import tkinter"

The GUI requires tkinter. Install it:

```bash
# Ubuntu/Debian
sudo apt install python3-tk

# Fedora
sudo dnf install python3-tkinter

# Arch
sudo pacman -S tk
```

TUI and CLI do not require tkinter.

### "Permission denied" when rebuilding

The executable may be running. Close it before rebuilding.

### Termux: "Permission denied" on tdminer

```bash
chmod +x ~/.local/bin/tdminer
# Or for system-wide install:
chmod +x $PREFIX/bin/tdminer
```

### Termux: build errors with C extensions

```bash
pkg install clang python
# Then retry the install
```

### Linux AppImage won't start

Ensure FUSE is available:

```bash
# Ubuntu/Debian
sudo apt install fuse libfuse2

# The AppImage may need to be marked executable
chmod +x *.AppImage
```

### GUI shows blank window on headless Linux

The GUI requires a display server (X11 or Wayland). For headless builds, use `xvfb-run`. For running, use the TUI or CLI frontend instead.

### "ModuleNotFoundError" when running from source

Ensure you activated the virtual environment and installed the correct requirements:

```bash
# For GUI
pip install -r requirements.txt

# For TUI/CLI
pip install -r requirements-tui.txt
```

### TUI shows garbled output

Ensure your terminal supports Unicode and ANSI colors. Most modern terminals work. For minimal terminals, use the CLI mode:

```bash
tdminer cli
```
