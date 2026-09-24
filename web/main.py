from __future__ import annotations

import argparse
import asyncio
import getpass
import logging
import os
import secrets
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aiohttp import web

from core.constants import ClientType, WORKING_DIR
from core.exceptions import CaptchaRequired, LoginException
from core.settings import Settings
from core.utils import CHARS_HEX_LOWER, create_nonce
from network.twitch import Twitch, import_auth_token
from web.auth import AuthStore, PASSWORD_MIN_LENGTH, validate_password
from web.server import create_app


DEFAULT_PORT = 17473


class _TerminalLogin:
    def __init__(self) -> None:
        self.username = ""
        self.password = ""
        self.needs_code = False

    async def ask_login(self) -> SimpleNamespace:
        while not self.username:
            self.username = input("Twitch username: ").strip()
        while not self.password:
            self.password = getpass.getpass("Twitch password: ")
        code = getpass.getpass("Twitch 2FA or email code: ").strip() if self.needs_code else ""
        self.needs_code = True
        return SimpleNamespace(username=self.username, password=self.password, token=code)

    def clear(self, login: bool = False, password: bool = False, token: bool = False) -> None:
        if not login and not password and not token:
            login = password = True
        if login:
            self.username = ""
        if password:
            self.password = ""
            self.needs_code = False


class _TerminalManager:
    def __init__(self, _twitch: Twitch) -> None:
        self.login = _TerminalLogin()
        self.close_requested = False
        self._closed = asyncio.Event()

    @staticmethod
    def print(message: str) -> None:
        print(message)

    async def coro_unless_closed(self, awaitable: Any) -> Any:
        return await awaitable

    async def wait_until_closed(self) -> None:
        await self._closed.wait()


def _password(confirm: bool = True) -> str:
    password = os.environ.get("TDMINER_ADMIN_PASSWORD") or getpass.getpass(
        f"New admin password ({PASSWORD_MIN_LENGTH}+ characters): "
    )
    try:
        validate_password(password)
    except ValueError as exc:
        raise SystemExit(f"Invalid password: {exc}") from None
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


def import_twitch_session() -> int:
    token = getpass.getpass("Twitch auth-token cookie: ")
    try:
        result = asyncio.run(import_auth_token(token))
    except ValueError as exc:
        raise SystemExit(f"Token not imported: {exc}") from None
    print(
        f"Twitch session imported for user {result['user_id']} "
        f"({result['client']}, {result['campaign_count']} campaigns visible)."
    )
    return 0


async def _login_twitch_android() -> dict[str, Any]:
    args = Namespace(
        log=False,
        tray=False,
        dump=False,
        logging_level=logging.WARNING,
        debug_ws=logging.NOTSET,
        debug_gql=logging.NOTSET,
    )
    client = Twitch(Settings(args), gui_factory=_TerminalManager)
    client._client_type = ClientType.ANDROID_APP
    client._auth_state.device_id = create_nonce(CHARS_HEX_LOWER, 32)
    try:
        token = await client._auth_state._login()
    finally:
        if client._session is not None:
            await client._session.close()
            client._session = None
    return await import_auth_token(token)


def login_twitch() -> int:
    if not sys.stdin.isatty():
        raise SystemExit("Twitch login requires an interactive terminal.")
    print("Credentials are sent directly to Twitch and are not saved by DropForge.")
    try:
        result = asyncio.run(_login_twitch_android())
    except CaptchaRequired:
        raise SystemExit(
            "Twitch requires a CAPTCHA for this login. "
            "Wait before retrying or log in from a trusted network."
        ) from None
    except (LoginException, ValueError) as exc:
        raise SystemExit(f"Twitch login failed: {exc}") from None
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("Twitch login cancelled.") from None
    print(
        f"Twitch Android session saved for user {result['user_id']} "
        f"({result['campaign_count']} campaigns visible)."
    )
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
    parser = argparse.ArgumentParser(description="DropForge self-hosted Twitch drops web UI")
    sub = parser.add_subparsers(dest="command", required=True)
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default=os.environ.get("TDMINER_HOST", "127.0.0.1"))
    serve_parser.add_argument(
        "--port", type=int, default=int(os.environ.get("TDMINER_PORT", DEFAULT_PORT))
    )
    serve_parser.add_argument("--no-auto-start", action="store_true")
    sub.add_parser("provision")
    sub.add_parser("reset-password")
    sub.add_parser("import-twitch-token")
    sub.add_parser("login-twitch")
    args = parser.parse_args(argv)
    if args.command == "provision":
        return provision()
    if args.command == "reset-password":
        return reset_password()
    if args.command == "import-twitch-token":
        return import_twitch_session()
    if args.command == "login-twitch":
        return login_twitch()
    return serve(args.host, args.port, args.no_auto_start)


if __name__ == "__main__":
    raise SystemExit(main())
