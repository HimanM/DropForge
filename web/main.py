from __future__ import annotations

import argparse
import getpass
import os
import secrets
from pathlib import Path

from aiohttp import web

from core.constants import WORKING_DIR
from web.auth import AuthStore
from web.server import create_app


DEFAULT_PORT = 17473


def _password(confirm: bool = True) -> str:
    password = os.environ.get("TDMINER_ADMIN_PASSWORD") or getpass.getpass("New admin password: ")
    if confirm and "TDMINER_ADMIN_PASSWORD" not in os.environ:
        if password != getpass.getpass("Confirm admin password: "):
            raise SystemExit("Passwords do not match.")
    return password


def provision() -> int:
    store = AuthStore(Path(WORKING_DIR, "web-auth.sqlite3"))
    password = _password()
    recovery = os.environ.get("TDMINER_RECOVERY_CODE") or secrets.token_urlsafe(24)
    if not store.provision(password, recovery):
        print("Web authentication is already provisioned. Existing credentials were preserved.")
        return 0
    print("Web authentication provisioned.")
    print(f"Admin password: {password}")
    print(f"Recovery code: {recovery}")
    print("Store the recovery code somewhere safe. It is rotated after every reset.")
    return 0


def reset_password() -> int:
    store = AuthStore(Path(WORKING_DIR, "web-auth.sqlite3"))
    recovery = store.force_password(_password())
    print("Password reset. Existing browser sessions were revoked.")
    print(f"New recovery code: {recovery}")
    return 0


def serve(host: str, port: int, no_auto_start: bool) -> int:
    auth_path = Path(WORKING_DIR, "web-auth.sqlite3")
    if not AuthStore(auth_path).is_provisioned():
        raise SystemExit("Web authentication is not provisioned. Run: python tdminer_web.py provision")
    static_path = Path(__file__).resolve().parent / "static"
    app = create_app(auth_path, static_path, auto_start=not no_auto_start)
    web.run_app(app, host=host, port=port, print=lambda line: print(f"DropForge: {line}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DropForge self-hosted Twitch Drops Miner web UI")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default=os.environ.get("TDMINER_HOST", "127.0.0.1"))
    serve_parser.add_argument(
        "--port", type=int, default=int(os.environ.get("TDMINER_PORT", DEFAULT_PORT))
    )
    serve_parser.add_argument("--no-auto-start", action="store_true")
    sub.add_parser("provision")
    sub.add_parser("reset-password")
    args = parser.parse_args(argv)
    if args.command == "provision":
        return provision()
    if args.command == "reset-password":
        return reset_password()
    return serve(args.host, args.port, args.no_auto_start)


if __name__ == "__main__":
    raise SystemExit(main())
