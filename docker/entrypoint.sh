#!/bin/sh
set -eu

mkdir -p "$TDMINER_DATA_DIR"
chmod 700 "$TDMINER_DATA_DIR"

if ! python -c 'from pathlib import Path; from core.constants import WORKING_DIR; from web.auth import AuthStore; raise SystemExit(0 if AuthStore(Path(WORKING_DIR, "web-auth.sqlite3")).is_provisioned() else 1)'; then
  if [ -z "${TDMINER_ADMIN_PASSWORD:-}" ]; then
    TDMINER_ADMIN_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(18))')"
    export TDMINER_ADMIN_PASSWORD
    printf '\nDropForge generated an admin password for this first start:\n  %s\n\n' "$TDMINER_ADMIN_PASSWORD"
  fi
  python tdminer_web.py provision
fi

exec python tdminer_web.py serve --host "$TDMINER_HOST" --port "$TDMINER_PORT"
