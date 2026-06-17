#!/usr/bin/env sh
set -eu

REPO="${TDMINER_REPO:-HimanM/TwitchDropsMiner}"
REF="${TDMINER_REF:-main}"
INSTALL_DIR="${TDMINER_INSTALL_DIR:-$HOME/.local/bin}"
APP_DIR="${TDMINER_APP_DIR:-$HOME/.local/share/tdminer}"
DATA_DIR="$APP_DIR/data"

migrate_data_file() {
  src="$1"
  name="$2"
  if [ -e "$src/$name" ] && [ ! -e "$DATA_DIR/$name" ]; then
    mkdir -p "$DATA_DIR"
    mv "$src/$name" "$DATA_DIR/$name"
  fi
}

os="$(uname -s)"
arch="$(uname -m)"

if [ -n "${TERMUX_VERSION:-}" ] || [ -n "${ANDROID_ROOT:-}" ]; then
  if [ -z "${TDMINER_INSTALL_DIR+x}" ] && [ -n "${PREFIX:-}" ]; then
    INSTALL_DIR="$PREFIX/bin"
  fi

  for cmd in curl tar python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
      echo "Missing required command: $cmd" >&2
      echo "On Termux, run: pkg install python clang curl tar" >&2
      exit 1
    fi
  done

  if ! python3 -m venv --help >/dev/null 2>&1; then
    echo "Python venv support is required." >&2
    echo "On Termux, run: pkg install python" >&2
    exit 1
  fi

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  archive_url="https://github.com/$REPO/archive/$REF.tar.gz"

  echo "Installing tdminer from source for Termux/Android."
  echo "Downloading $archive_url"
  curl -fL "$archive_url" -o "$tmp_dir/source.tar.gz"
  tar -xzf "$tmp_dir/source.tar.gz" -C "$tmp_dir"
  extracted="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  if [ -z "$extracted" ]; then
    echo "Could not extract tdminer source archive." >&2
    exit 1
  fi

  mkdir -p "$APP_DIR" "$INSTALL_DIR" "$DATA_DIR"
  migrate_data_file "$APP_DIR/source" "cookies.jar"
  migrate_data_file "$APP_DIR/source" "settings.json"
  if [ -d "$APP_DIR/source/cache" ] && [ ! -d "$DATA_DIR/cache" ]; then
    mv "$APP_DIR/source/cache" "$DATA_DIR/cache"
  fi

  rm -rf "$APP_DIR/source"
  mv "$extracted" "$APP_DIR/source"

  python3 -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/python" -m pip install --upgrade pip
  "$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/source/requirements-tui.txt"

  cat > "$INSTALL_DIR/tdminer" <<EOF
#!/usr/bin/env sh
if [ "\$#" -eq 0 ]; then
  set -- cli
fi
export TDMINER_DATA_DIR="$DATA_DIR"
exec "$APP_DIR/venv/bin/python" "$APP_DIR/source/tdminer.py" "\$@"
EOF
  chmod +x "$INSTALL_DIR/tdminer"

  echo "Installed tdminer source launcher to $INSTALL_DIR/tdminer"
  echo "Persistent data: $DATA_DIR"
  echo "Run: tdminer"
  echo "Run explicitly: tdminer cli"
  exit 0
fi

for cmd in curl unzip; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
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

mkdir -p "$INSTALL_DIR" "$APP_DIR/bin" "$DATA_DIR"
echo "Downloading $url"
curl -fL "$url" -o "$tmp_dir/tdminer.zip"
unzip -q "$tmp_dir/tdminer.zip" -d "$tmp_dir"

found="$(find "$tmp_dir" -type f -name "$binary" | head -n 1)"
if [ -z "$found" ]; then
  echo "Could not find $binary in release asset." >&2
  exit 1
fi

migrate_data_file "$INSTALL_DIR" "cookies.jar"
migrate_data_file "$INSTALL_DIR" "settings.json"
if [ -d "$INSTALL_DIR/cache" ] && [ ! -d "$DATA_DIR/cache" ]; then
  mv "$INSTALL_DIR/cache" "$DATA_DIR/cache"
fi

cp "$found" "$APP_DIR/bin/tdminer"
chmod +x "$APP_DIR/bin/tdminer"

cat > "$INSTALL_DIR/tdminer" <<EOF
#!/usr/bin/env sh
export TDMINER_DATA_DIR="$DATA_DIR"
exec "$APP_DIR/bin/tdminer" "\$@"
EOF
chmod +x "$INSTALL_DIR/tdminer"

echo "Installed tdminer to $INSTALL_DIR/tdminer"
echo "Persistent data: $DATA_DIR"
case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *)
    echo "Add this to your shell profile if tdminer is not found:"
    echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
    ;;
esac
echo "Run: tdminer"
