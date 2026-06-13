#!/usr/bin/env sh
set -eu

REPO="${TDMINER_REPO:-HimanM/TwitchDropsMiner}"
INSTALL_DIR="${TDMINER_INSTALL_DIR:-$HOME/.local/bin}"

os="$(uname -s)"
arch="$(uname -m)"

if [ -n "${TERMUX_VERSION:-}" ] || [ -n "${ANDROID_ROOT:-}" ]; then
  echo "Native Termux/Android is not supported by the tdminer release binaries." >&2
  echo "Use a glibc Linux environment such as proot Ubuntu/Debian if you want to experiment." >&2
  exit 1
fi

for command in curl unzip; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
done

case "$os" in
  Linux)
    case "$arch" in
      x86_64|amd64) asset="Twitch.Drops.Miner.TUI.Linux-x86_64.zip" ;;
      aarch64|arm64) asset="Twitch.Drops.Miner.TUI.Linux-aarch64.zip" ;;
      *) echo "Unsupported Linux architecture: $arch" >&2; exit 1 ;;
    esac
    binary="tdminer"
    ;;
  Darwin)
    asset="Twitch.Drops.Miner.TUI.MacOS.zip"
    binary="tdminer"
    ;;
  *)
    echo "Unsupported OS: $os" >&2
    exit 1
    ;;
esac

url="https://github.com/$REPO/releases/latest/download/$asset"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "$INSTALL_DIR"
echo "Downloading $url"
curl -fL "$url" -o "$tmp_dir/tdminer.zip"
unzip -q "$tmp_dir/tdminer.zip" -d "$tmp_dir"

found="$(find "$tmp_dir" -type f -name "$binary" | head -n 1)"
if [ -z "$found" ]; then
  echo "Could not find $binary in release asset." >&2
  exit 1
fi

cp "$found" "$INSTALL_DIR/tdminer"
chmod +x "$INSTALL_DIR/tdminer"

echo "Installed tdminer to $INSTALL_DIR/tdminer"
case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *)
    echo "Add this to your shell profile if tdminer is not found:"
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    ;;
esac
echo "Run: tdminer"
