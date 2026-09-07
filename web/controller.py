from __future__ import annotations

import asyncio
import io
import logging
import traceback
from argparse import Namespace
from time import monotonic
from typing import Any

from core.constants import COOKIES_PATH, FILE_FORMATTER, LOCK_PATH, LOG_PATH
from core.exceptions import CaptchaRequired
from core.settings import Settings
from core.translate import _
from core.utils import ExponentialBackoff, lock_file
from network.twitch import Twitch
from web.discord import DiscordNotifier
from web.manager import WebManager


class MinerController:
    def __init__(self, notifier: DiscordNotifier | None = None) -> None:
        self.notifier = notifier
        self.manager: WebManager | None = None
        self._client: Twitch | None = None
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._instance_lock: io.TextIOWrapper | None = None
        self._logging_configured = False
        self._stop_requested = asyncio.Event()
        self.last_error = ""

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> bool:
        async with self._lock:
            if self.running:
                return False
            self.last_error = ""
            self._stop_requested.clear()
            self._task = asyncio.create_task(self._run(), name="tdminer")
            await asyncio.sleep(0)
            return True

    async def stop(self, *, notify: bool = True) -> bool:
        async with self._lock:
            if not self.running:
                return False
            self._stop_requested.set()
            task = self._task
            if notify and self.notifier is not None and self.manager is not None:
                self.notifier.miner_stopped(self.manager)
            if self.manager is not None:
                self.manager.close()
        if task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=20)
            except asyncio.TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        return True

    async def close(self) -> None:
        if self.running:
            await self.stop(notify=False)

    async def reset_auth(self) -> bool:
        if self.running:
            if self.manager is None:
                return False
            self.manager.invalidate_auth()
            return True
        COOKIES_PATH.unlink(missing_ok=True)
        return await self.start()

    async def _run(self) -> None:
        backoff = ExponentialBackoff(variance=0, maximum=60)
        while not self._stop_requested.is_set():
            started = monotonic()
            restart = await self._run_once()
            if not restart or self._stop_requested.is_set():
                return
            if monotonic() - started >= 5 * 60:
                backoff.reset()
            delay = min(5 * next(backoff), 60)
            logger = logging.getLogger("TwitchDrops")
            logger.warning("Miner engine restarting automatically in %d seconds", delay)
            if self.notifier is not None:
                self.notifier.operational(
                    "Miner restarting automatically",
                    f"DropForge encountered an unexpected error and will retry in {delay:.0f} seconds.",
                    event_key="miner-restart",
                )
            try:
                await asyncio.wait_for(self._stop_requested.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass

    async def _run_once(self) -> bool:
        success, instance_lock = lock_file(LOCK_PATH)
        if not success:
            self.last_error = f"Another tdminer instance is already running or the lock is busy: {LOCK_PATH}"
            return False
        self._instance_lock = instance_lock
        restart = False
        self.last_error = ""
        args = Namespace(
            log=True,
            tray=False,
            dump=False,
            logging_level=logging.INFO,
            debug_ws=logging.NOTSET,
            debug_gql=logging.NOTSET,
        )
        try:
            settings = Settings(args)
            if not self._logging_configured:
                logger = logging.getLogger("TwitchDrops")
                logger.setLevel(settings.logging_level)
                if settings.log:
                    handler = logging.FileHandler(LOG_PATH)
                    handler.setFormatter(FILE_FORMATTER)
                    logger.addHandler(handler)
                logging.getLogger("TwitchDrops.gql").setLevel(settings.debug_gql)
                logging.getLogger("TwitchDrops.websocket").setLevel(settings.debug_ws)
                self._logging_configured = True
            client = Twitch(
                settings,
                gui_factory=lambda twitch: WebManager(twitch, self.notifier),
            )
            self._client = client
            self.manager = client.gui
            try:
                _.set_language(settings.language)
            except ValueError:
                pass
            await client.run()
        except CaptchaRequired:
            self.last_error = _("error", "captcha")
            if self._client is not None:
                self._client.print(self.last_error)
            if self.notifier is not None:
                self.notifier.operational("Twitch verification required", self.last_error)
        except asyncio.CancelledError:
            raise
        except Exception:
            restart = True
            self.last_error = traceback.format_exc()
            if self._client is not None:
                self._client.print("Fatal error encountered:")
                self._client.print(self.last_error)
        finally:
            if self._client is not None:
                await self._client.shutdown()
                self._client.save(force=True)
                self._client.gui.stop()
            self._client = None
            instance_lock.close()
            self._instance_lock = None
        return restart

    def snapshot(self) -> dict[str, Any]:
        state = self.manager.snapshot() if self.manager is not None else {
            "status": "Stopped",
            "icon_state": "idle",
            "login": {"status": "Miner stopped", "user_id": "-", "activation_url": "", "user_code": ""},
            "current_drop": {},
            "channels": [],
            "campaigns": [],
            "websockets": [],
            "settings": {},
            "notifications": self.notifier.snapshot() if self.notifier is not None else {},
            "selected_channel_id": None,
            "logs": [],
        }
        if not self.running:
            state["login"]["activation_url"] = ""
            state["login"]["user_code"] = ""
        state["notifications"] = self.notifier.snapshot() if self.notifier is not None else {}
        return {
            **state,
            "miner": {
                "running": self.running,
                "last_error": self.last_error,
            },
        }
