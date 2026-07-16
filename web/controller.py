from __future__ import annotations

import asyncio
import io
import logging
import traceback
from argparse import Namespace
from typing import Any

from core.constants import FILE_FORMATTER, LOCK_PATH, LOG_PATH
from core.exceptions import CaptchaRequired
from core.settings import Settings
from core.translate import _
from core.utils import lock_file
from network.twitch import Twitch
from web.manager import WebManager


class MinerController:
    def __init__(self) -> None:
        self.manager: WebManager | None = None
        self._client: Twitch | None = None
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._instance_lock: io.TextIOWrapper | None = None
        self._logging_configured = False
        self.last_error = ""

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> bool:
        async with self._lock:
            if self.running:
                return False
            self.last_error = ""
            self._task = asyncio.create_task(self._run(), name="tdminer")
            await asyncio.sleep(0)
            return True

    async def stop(self) -> bool:
        async with self._lock:
            if not self.running or self.manager is None:
                return False
            task = self._task
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
            await self.stop()

    async def _run(self) -> None:
        success, instance_lock = lock_file(LOCK_PATH)
        if not success:
            self.last_error = f"Another tdminer instance is already running or the lock is busy: {LOCK_PATH}"
            return
        self._instance_lock = instance_lock
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
            client = Twitch(settings, gui_factory=WebManager)
            self._client = client
            self.manager = client.gui
            try:
                _.set_language(settings.language)
            except ValueError:
                pass
            await client.run()
        except CaptchaRequired:
            self.last_error = _("error", "captcha")
            client.print(self.last_error)
        except asyncio.CancelledError:
            raise
        except Exception:
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
            "selected_channel_id": None,
            "logs": [],
        }
        if not self.running:
            state["login"]["activation_url"] = ""
            state["login"]["user_code"] = ""
        return {
            **state,
            "miner": {
                "running": self.running,
                "last_error": self.last_error,
            },
        }
