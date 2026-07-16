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

if [ "$os" = "Linux" ]; then
  MODE_FILE="$APP_DIR/install-mode"
  if [ -n "${TDMINER_MODE:-}" ]; then
    INSTALL_MODE="$TDMINER_MODE"
  elif [ -f "$MODE_FILE" ]; then
    INSTALL_MODE="$(cat "$MODE_FILE")"
  elif [ -r /dev/tty ]; then
    printf '\nChoose the Linux interface:\n  1) Web UI (recommended)\n  2) CLI\nSelection [1]: ' > /dev/tty
    IFS= read -r mode_choice < /dev/tty || mode_choice=""
    case "$mode_choice" in
      2|cli|CLI) INSTALL_MODE="cli" ;;
      *) INSTALL_MODE="web" ;;
    esac
  else
    INSTALL_MODE="web"
    echo "No interactive terminal detected; installing the Web UI. Set TDMINER_MODE=cli to choose CLI."
  fi
  case "$INSTALL_MODE" in
    web|cli) ;;
    *) echo "TDMINER_MODE must be 'web' or 'cli'." >&2; exit 1 ;;
  esac

  PORT="${TDMINER_PORT:-17473}"
  HOST_FILE="$APP_DIR/web-host"
  HOST="${TDMINER_HOST:-}"
  SERVICE_NAME="tdminer-web"

  if [ "$INSTALL_MODE" = "web" ]; then
    if [ -z "$HOST" ] && [ -f "$HOST_FILE" ]; then
      HOST="$(cat "$HOST_FILE")"
    elif [ -z "$HOST" ] && [ -r /dev/tty ]; then
      printf '\nChoose Web UI exposure:\n  1) Localhost only (recommended; use Tailscale for remote access)\n  2) All interfaces (0.0.0.0)\nSelection [1]: ' > /dev/tty
      IFS= read -r host_choice < /dev/tty || host_choice=""
      case "$host_choice" in
        2|0.0.0.0) HOST="0.0.0.0" ;;
        *) HOST="127.0.0.1" ;;
      esac
    fi
    [ -n "$HOST" ] || HOST="127.0.0.1"
    if [ "$HOST" = "localhost" ]; then
      HOST="127.0.0.1"
    fi
    case "$HOST" in
      127.0.0.1|0.0.0.0) ;;
      *) echo "TDMINER_HOST must be '127.0.0.1', 'localhost', or '0.0.0.0'." >&2; exit 1 ;;
    esac
    case "$PORT" in
      ''|*[!0-9]*) echo "TDMINER_PORT must be a number." >&2; exit 1 ;;
    esac
    if [ "$PORT" -lt 1024 ] || [ "$PORT" -gt 65535 ]; then
      echo "TDMINER_PORT must be between 1024 and 65535." >&2
      exit 1
    fi
  fi

  as_root() {
    if [ "$(id -u)" -eq 0 ]; then
      "$@"
    elif command -v sudo >/dev/null 2>&1; then
      sudo "$@"
    else
      echo "Root access is required to install the system service. Install sudo or run as root." >&2
      exit 1
    fi
  }

  install_dependencies() {
    if command -v apt-get >/dev/null 2>&1; then
      as_root apt-get update
      as_root apt-get install -y ca-certificates curl tar python3 python3-venv
    elif command -v dnf >/dev/null 2>&1; then
      as_root dnf install -y ca-certificates curl tar python3
    elif command -v pacman >/dev/null 2>&1; then
      as_root pacman -Sy --needed --noconfirm ca-certificates curl tar python
    else
      echo "Install curl, tar, Python 3, python3-venv, and systemd, then run this command again." >&2
      exit 1
    fi
  }

  if ! command -v curl >/dev/null 2>&1 \
    || ! command -v tar >/dev/null 2>&1 \
    || ! command -v python3 >/dev/null 2>&1; then
    install_dependencies
  fi
  if [ "$INSTALL_MODE" = "web" ] && ! command -v systemctl >/dev/null 2>&1; then
    echo "DropForge currently requires a systemd-based Linux server." >&2
    exit 1
  fi

  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' EXIT
  if ! python3 -m venv "$tmp_dir/venv-check" >/dev/null 2>&1; then
    install_dependencies
  fi
  rm -rf "$tmp_dir/venv-check"

  archive_url="https://github.com/$REPO/archive/$REF.tar.gz"
  release_id="$(date -u +%Y%m%d%H%M%S)-$$"
  release_dir="$APP_DIR/releases/$release_id"
  service_user="$(id -un)"
  service_group="$(id -gn)"

  echo "Installing tdminer $INSTALL_MODE interface from $archive_url"
  curl -fL "$archive_url" -o "$tmp_dir/source.tar.gz"
  tar -xzf "$tmp_dir/source.tar.gz" -C "$tmp_dir"
  extracted="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d ! -name venv-check | head -n 1)"
  if [ -z "$extracted" ]; then
    echo "Could not extract DropForge source." >&2
    exit 1
  fi

  mkdir -p "$APP_DIR/releases" "$DATA_DIR" "$INSTALL_DIR"
  chmod 700 "$DATA_DIR"
  migrate_data_file "$APP_DIR/source" "cookies.jar"
  migrate_data_file "$APP_DIR/source" "settings.json"
  if [ -d "$APP_DIR/source/cache" ] && [ ! -d "$DATA_DIR/cache" ]; then
    mv "$APP_DIR/source/cache" "$DATA_DIR/cache"
  fi
  migrate_data_file "$INSTALL_DIR" "cookies.jar"
  migrate_data_file "$INSTALL_DIR" "settings.json"
  if [ -d "$INSTALL_DIR/cache" ] && [ ! -d "$DATA_DIR/cache" ]; then
    mv "$INSTALL_DIR/cache" "$DATA_DIR/cache"
  fi

  mv "$extracted" "$release_dir"
  python3 -m venv "$release_dir/venv"
  "$release_dir/venv/bin/python" -m pip install --upgrade pip
  if [ "$INSTALL_MODE" = "web" ]; then
    requirements_file="requirements-web.txt"
  else
    requirements_file="requirements-tui.txt"
  fi
  "$release_dir/venv/bin/python" -m pip install -r "$release_dir/$requirements_file"

  previous_release=""
  if [ -L "$APP_DIR/current" ]; then
    previous_release="$(readlink "$APP_DIR/current")"
  fi

  if [ "$INSTALL_MODE" = "cli" ]; then
    if [ -f "/etc/systemd/system/$SERVICE_NAME.service" ]; then
      as_root systemctl disable --now "$SERVICE_NAME.service"
    fi
    rm -f "$APP_DIR/current.new"
    ln -s "$release_dir" "$APP_DIR/current.new"
    mv -Tf "$APP_DIR/current.new" "$APP_DIR/current"
    cat > "$INSTALL_DIR/tdminer" <<EOF
#!/usr/bin/env sh
export TDMINER_DATA_DIR="$DATA_DIR"
exec "$APP_DIR/current/venv/bin/python" "$APP_DIR/current/tdminer.py" cli "\$@"
EOF
    chmod +x "$INSTALL_DIR/tdminer"
    rm -f "$INSTALL_DIR/tdminer-web"
    printf '%s\n' cli > "$MODE_FILE"
    echo "tdminer CLI is installed."
    echo "Persistent data: $DATA_DIR"
    echo "Run: $INSTALL_DIR/tdminer"
    echo "Run the same curl command again to update. Use TDMINER_MODE=web to switch interfaces."
    exit 0
  fi

  server_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  [ -n "$server_ip" ] || server_ip="SERVER_IP"
  if [ "$HOST" = "127.0.0.1" ]; then
    access_url="http://127.0.0.1:$PORT"
  else
    access_url="http://$server_ip:$PORT"
  fi

  if [ ! -f "$DATA_DIR/web-auth.sqlite3" ]; then
    admin_password="${TDMINER_ADMIN_PASSWORD:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')}"
    recovery_code="${TDMINER_RECOVERY_CODE:-$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')}"
    TDMINER_DATA_DIR="$DATA_DIR" \
      TDMINER_ADMIN_PASSWORD="$admin_password" \
      TDMINER_RECOVERY_CODE="$recovery_code" \
      "$release_dir/venv/bin/python" "$release_dir/tdminer_web.py" provision >/dev/null
    echo ""
    echo "============================================================"
    echo "  DropForge Web Access"
    echo "============================================================"
    printf '  Access URL      %s\n' "$access_url"
    printf '  Server IP       %s\n' "$server_ip"
    printf '  Bind address    %s\n' "$HOST"
    printf '  Port            %s\n' "$PORT"
    echo "------------------------------------------------------------"
    echo "  SAVE THESE CREDENTIALS"
    printf '  Admin password  %s\n' "$admin_password"
    printf '  Recovery code   %s\n' "$recovery_code"
    echo "============================================================"
    echo "The recovery code is rotated after every password reset."
  else
    echo "Existing web password, sessions, Twitch cookies, and settings preserved."
  fi

  rm -f "$APP_DIR/current.new"
  ln -s "$release_dir" "$APP_DIR/current.new"
  mv -Tf "$APP_DIR/current.new" "$APP_DIR/current"

  cat > "$tmp_dir/$SERVICE_NAME.service" <<EOF
[Unit]
Description=DropForge Web UI
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$service_user
Group=$service_group
WorkingDirectory=$APP_DIR/current
Environment="TDMINER_DATA_DIR=$DATA_DIR"
Environment="TDMINER_HOST=$HOST"
Environment="TDMINER_PORT=$PORT"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$APP_DIR/current/venv/bin/python $APP_DIR/current/tdminer_web.py serve
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$DATA_DIR $APP_DIR/current/lang

[Install]
WantedBy=multi-user.target
EOF
  as_root cp "$tmp_dir/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
  as_root systemctl daemon-reload
  as_root systemctl enable "$SERVICE_NAME.service"
  service_started=true
  if ! as_root systemctl restart "$SERVICE_NAME.service"; then
    service_started=false
  else
    sleep 2
    if ! as_root systemctl is-active --quiet "$SERVICE_NAME.service"; then
      service_started=false
    fi
  fi
  if [ "$service_started" = "false" ]; then
    if [ -n "$previous_release" ]; then
      rm -f "$APP_DIR/current.rollback"
      ln -s "$previous_release" "$APP_DIR/current.rollback"
      mv -Tf "$APP_DIR/current.rollback" "$APP_DIR/current"
      as_root systemctl restart "$SERVICE_NAME.service" || true
    else
      as_root systemctl stop "$SERVICE_NAME.service" || true
      rm -f "$APP_DIR/current"
    fi
    echo "DropForge failed to start. Run: sudo journalctl -u $SERVICE_NAME.service -n 100 --no-pager" >&2
    exit 1
  fi

  cat > "$INSTALL_DIR/tdminer-web" <<EOF
#!/usr/bin/env sh
set -eu
case "\${1:-status}" in
  reset-password)
    export TDMINER_DATA_DIR="$DATA_DIR"
    exec "$APP_DIR/current/venv/bin/python" "$APP_DIR/current/tdminer_web.py" reset-password
    ;;
  start|stop|restart|status)
    if [ "\$(id -u)" -eq 0 ]; then
      exec systemctl "\${1:-status}" "$SERVICE_NAME.service"
    fi
    exec sudo systemctl "\${1:-status}" "$SERVICE_NAME.service"
    ;;
  logs)
    if [ "\$(id -u)" -eq 0 ]; then
      exec journalctl -u "$SERVICE_NAME.service" -f
    fi
    exec sudo journalctl -u "$SERVICE_NAME.service" -f
    ;;
  *)
    echo "Usage: tdminer-web {status|start|stop|restart|logs|reset-password}" >&2
    exit 2
    ;;
esac
EOF
  chmod +x "$INSTALL_DIR/tdminer-web"
  rm -f "$INSTALL_DIR/tdminer"
  printf '%s\n' web > "$MODE_FILE"
  printf '%s\n' "$HOST" > "$HOST_FILE"

  if [ "$HOST" = "0.0.0.0" ] && command -v ufw >/dev/null 2>&1 && as_root ufw status 2>/dev/null | grep -q '^Status: active'; then
    as_root ufw allow "$PORT/tcp" comment DropForge
  fi

  echo ""
  echo "DropForge is installed and running."
  if [ "$HOST" = "127.0.0.1" ]; then
    echo "Open locally: $access_url"
    echo "Recommended private remote access: tailscale serve --bg http://127.0.0.1:$PORT"
  else
    echo "Open: $access_url"
    echo "Warning: 0.0.0.0 exposes DropForge to every reachable network interface."
  fi
  echo "Persistent data: $DATA_DIR"
  echo "Service helper: $INSTALL_DIR/tdminer-web"
  echo "Run the same curl command again to update without replacing data or browser sessions."
  echo "Use TDMINER_MODE=cli to switch interfaces."
  # ponytail: releases are retained for rollback; add retention after storage becomes measurable.
  exit 0
fi

for cmd in curl unzip; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Missing required command: $cmd" >&2
    exit 1
  fi
done

case "$os" in
  Darwin)
    asset="DropForge.TUI.MacOS.zip"
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
