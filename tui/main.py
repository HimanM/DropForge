from __future__ import annotations

import argparse
import asyncio
import io
import logging
import signal
import sys
import traceback
import warnings
from typing import NoReturn, TYPE_CHECKING

from core.constants import FILE_FORMATTER, LOCK_PATH, LOG_PATH, LOGGING_LEVELS, SELF_PATH
from core.exceptions import CaptchaRequired
from core.settings import Settings
from core.translate import _
from core.utils import lock_file
from network.twitch import Twitch
from tui.cli import PortableCLIManager
from tui.manager import TUIManager
from version import __version__

try:
    import truststore
except ImportError:
    truststore = None

if TYPE_CHECKING:
    from _typeshed import SupportsWrite


class Parser(argparse.ArgumentParser):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._message = io.StringIO()

    def _print_message(self, message: str, file: SupportsWrite[str] | None = None) -> None:
        self._message.write(message)

    def exit(self, status: int = 0, message: str | None = None) -> NoReturn:
        if message:
            self._message.write(message)
        if status:
            raise SystemExit(f"Argument Parser Error\n{self._message.getvalue()}")
        output = self._message.getvalue()
        if output:
            print(output, end="")
        raise SystemExit(status)


class ParsedArgs(argparse.Namespace):
    _verbose: int
    _debug_ws: bool
    _debug_gql: bool
    log: bool
    tray: bool
    dump: bool
    frontend: str

    @property
    def logging_level(self) -> int:
        return LOGGING_LEVELS[min(self._verbose, 4)]

    @property
    def debug_ws(self) -> int:
        if self._debug_ws:
            return logging.DEBUG
        if self._verbose >= 4:
            return logging.INFO
        return logging.NOTSET

    @property
    def debug_gql(self) -> int:
        if self._debug_gql:
            return logging.DEBUG
        if self._verbose >= 4:
            return logging.INFO
        return logging.NOTSET


def parse_args(argv: list[str] | None = None) -> ParsedArgs:
    parser = Parser(
        SELF_PATH.name,
        description="A terminal UI for mining timed Twitch drops.",
    )
    parser.add_argument("--version", action="version", version=f"v{__version__}")
    parser.add_argument(
        "frontend",
        nargs="?",
        choices=("auto", "tui", "cli"),
        default="auto",
        help="Frontend to run. Use cli for portable Windows/Termux-style terminals.",
    )
    parser.add_argument("-v", dest="_verbose", action="count", default=0)
    parser.add_argument("--log", action="store_true")
    parser.add_argument("--dump", action="store_true")
    parser.add_argument("--tray", action="store_false", default=False, help=argparse.SUPPRESS)
    parser.add_argument("--debug-ws", dest="_debug_ws", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--debug-gql", dest="_debug_gql", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv, namespace=ParsedArgs())


def configure_logging(settings: Settings) -> None:
    if settings.logging_level > logging.DEBUG:
        logging.getLogger().addHandler(logging.NullHandler())
    logger = logging.getLogger("TwitchDrops")
    logger.setLevel(settings.logging_level)
    if settings.log:
        handler = logging.FileHandler(LOG_PATH)
        handler.setFormatter(FILE_FORMATTER)
        logger.addHandler(handler)
    logging.getLogger("TwitchDrops.gql").setLevel(settings.debug_gql)
    logging.getLogger("TwitchDrops.websocket").setLevel(settings.debug_ws)


def frontend_factory(name: str):
    if name == "cli":
        return PortableCLIManager
    if name == "tui":
        return TUIManager
    if sys.platform == "win32":
        return PortableCLIManager
    return TUIManager


async def run_client(settings: Settings, *, frontend: str = "auto") -> int:
    try:
        _.set_language(settings.language)
    except ValueError:
        pass

    configure_logging(settings)
    client = Twitch(settings, gui_factory=frontend_factory(frontend))
    loop = asyncio.get_running_loop()
    supports_signals = sys.platform != "win32"
    if supports_signals:
        loop.add_signal_handler(signal.SIGINT, lambda *_: client.gui.close())
        loop.add_signal_handler(signal.SIGTERM, lambda *_: client.gui.close())

    exit_status = 0
    try:
        await client.run()
    except CaptchaRequired:
        exit_status = 1
        client.prevent_close()
        client.print(_("error", "captcha"))
    except Exception:
        exit_status = 1
        client.prevent_close()
        client.print("Fatal error encountered:")
        client.print(traceback.format_exc())
    finally:
        if supports_signals:
            loop.remove_signal_handler(signal.SIGINT)
            loop.remove_signal_handler(signal.SIGTERM)
        client.print(_("gui", "status", "exiting"))
        await client.shutdown()

    if not client.gui.close_requested:
        client.gui.tray.change_icon("error")
        client.print(_("status", "terminated"))
        client.gui.status.update(_("gui", "status", "terminated"))
        client.gui.grab_attention(sound=False)
        await client.gui.wait_until_closed()

    client.save(force=True)
    client.gui.stop()
    client.gui.close_window()
    return exit_status


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if sys.platform == "win32" and args.frontend == "tui":
        raise SystemExit(
            "tdminer TUI is only supported on Linux and macOS. Use the GUI build on Windows."
        )
    if truststore is not None:
        truststore.inject_into_ssl()
    warnings.simplefilter("default", ResourceWarning)
    if sys.version_info < (3, 10):
        raise RuntimeError("Python 3.10 or higher is required")

    settings = Settings(args)
    success, file = lock_file(LOCK_PATH)
    if not success:
        return 3
    try:
        return asyncio.run(run_client(settings, frontend=args.frontend))
    finally:
        file.close()
