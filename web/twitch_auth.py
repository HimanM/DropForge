"""Browser-free authorization for the web server; desktop auth is unchanged."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from time import monotonic
from uuid import uuid4

import aiohttp
from yarl import URL

from core.constants import ClientInfo, State, WORKING_DIR
from core.exceptions import LoginException
from network.twitch import _AuthState


logger = logging.getLogger("TwitchDrops")
DEVICE_SESSION_PATH = Path(WORKING_DIR, "web-device-session.json")
TV_CLIENT = ClientInfo(
    URL("https://www.twitch.tv"),
    "ue6666qo983tsx6so1t0vnawi233wa",
    "Mozilla/5.0 (Linux; Android 7.1; Smart Box C1) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
)


class DeviceCookies(aiohttp.CookieJar):
    def save(self, file_path) -> None:
        # The shared engine saves cookies on shutdown; never overwrite browser cookies.
        return None


class WebDeviceAuth(_AuthState):
    def __init__(self, twitch, path: Path = DEVICE_SESSION_PATH):
        super().__init__(twitch)
        self.path = path
        self._validate_after = 0.0

    def clear(self) -> None:
        super().clear()
        self._validate_after = 0.0

    def invalidate(self, *, delete_cookies: bool = False) -> None:
        # GQL rejection alone is not proof of revocation. Recheck OAuth first.
        self.clear()

    async def get_integrity_token(self, *, force_refresh: bool = False) -> None:
        return None

    def _alert(self, kind: str, message: str, *, requires_login: bool = True, notify: bool = True) -> None:
        notifier = getattr(self._twitch.gui, "notifier", None)
        if notifier is not None:
            notifier.auth_issue(kind, message, requires_login=requires_login, notify=notify)

    def _load(self) -> dict:
        try:
            saved = json.loads(self.path.read_text(encoding="utf8"))
            if (
                isinstance(saved, dict)
                and isinstance(saved.get("access_token"), str)
                and 20 <= len(saved["access_token"]) <= 512
                and saved.get("client_id") == TV_CLIENT.CLIENT_ID
            ):
                return saved
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            logger.warning("Cannot read the saved web device session; activation is required")
        return {}

    def _save(self, token: str) -> None:
        temporary = self.path.with_suffix(".json.new")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf8") as stream:
                os.chmod(temporary, 0o600)
                json.dump({"access_token": token, "client_id": TV_CLIENT.CLIENT_ID,
                           "device_id": self.device_id}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.path)
        finally:
            temporary.unlink(missing_ok=True)

    async def _json(self, method: str, endpoint: str, **kwargs) -> tuple[int, dict]:
        session = await self._twitch.get_session()
        delay = 2
        while True:
            try:
                async def request():
                    async with session.request(method, "https://id.twitch.tv/oauth2/" + endpoint,
                                               proxy=self._twitch.settings.proxy or None, **kwargs) as response:
                        if response.status >= 500 or response.status == 429:
                            return response.status, {}
                        try:
                            body = await response.json()
                        except (ValueError, aiohttp.ContentTypeError):
                            raise LoginException("Twitch returned an unexpected authorization response.") from None
                        if not isinstance(body, dict):
                            raise LoginException("Twitch returned an unexpected authorization response.")
                        return response.status, body

                status, body = await self._twitch.gui.coro_unless_closed(request())
                if status < 500 and status != 429:
                    return status, body
            except (aiohttp.ClientError, asyncio.TimeoutError):
                pass
            self._twitch.print(f"Twitch authorization temporarily unavailable; retrying in {delay} seconds.")
            self._alert("connection", "Cannot reach Twitch authorization. Retrying without clearing the saved session.",
                        requires_login=False, notify=delay >= 8)
            await self._twitch.gui.coro_unless_closed(asyncio.sleep(delay))
            delay = min(delay * 2, 60)

    async def _oauth_login(self) -> str:
        gui = self._twitch.gui
        notifier = getattr(gui, "notifier", None)
        if notifier is not None and not notifier.auth_alert().get("requires_login"):
            self._alert("login_required", "Activate a Twitch device code in DropForge. No server browser is required.")
        while True:
            gui.status.update("Waiting for Twitch activation")
            status, device = await self._json("POST", "device", data={
                "client_id": TV_CLIENT.CLIENT_ID, "scopes": "",
            })
            if status != 200 or not all(isinstance(device.get(key), str) and device[key]
                                        for key in ("device_code", "user_code")):
                raise LoginException("Twitch device login is unavailable. Try again shortly.")
            try:
                interval = max(5, min(float(device.get("interval", 5)), 60))
                deadline = monotonic() + max(1, min(float(device.get("expires_in", 600)), 1800))
            except (TypeError, ValueError):
                raise LoginException("Twitch returned an invalid activation lifetime.") from None
            activation = URL("https://www.twitch.tv/activate").with_query({"device-code": device["user_code"]})
            await gui.login.ask_enter_code(activation, device["user_code"])
            while monotonic() < deadline:
                await gui.coro_unless_closed(asyncio.sleep(interval))
                status, body = await self._json("POST", "token", data={
                    "client_id": TV_CLIENT.CLIENT_ID, "device_code": device["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                })
                if status == 200 and isinstance(body.get("access_token"), str):
                    return body["access_token"]
                error = body.get("message") or body.get("error")
                if error == "slow_down":
                    interval = min(interval + 5, 60)
                elif error in {"expired_token", "access_denied"}:
                    break
                elif error != "authorization_pending":
                    raise LoginException("Twitch device authorization failed. Request a new activation code.")
            self._twitch.print("Twitch activation expired or was declined; requesting a new code.")

    async def _validate(self) -> None:
        if self._hasattrs("access_token", "user_id") and monotonic() < self._validate_after:
            return
        self._twitch._client_type = TV_CLIENT
        saved = self._load()
        self.device_id = str(saved.get("device_id") or uuid4().hex)
        self.session_id = getattr(self, "session_id", uuid4().hex)
        token = getattr(self, "access_token", None) or saved.get("access_token")
        revoked = False
        while True:
            new_login = not token
            if new_login:
                token = await self._oauth_login()
            status, identity = await self._json("GET", "validate", headers={"Authorization": f"OAuth {token}"})
            if status == 401:
                revoked = True
                self._twitch.stop_watching()
                self.clear()
                self.path.unlink(missing_ok=True)
                self._twitch.gui.login.update("Twitch activation required", None)
                self._twitch.print("The web device session is no longer valid; a new activation is required.")
                self._alert("expired", "Twitch expired or revoked the device session. Mining is paused until you activate a new code.")
                self.device_id, self.session_id = uuid4().hex, uuid4().hex
                token = None
                continue
            if status != 200 or identity.get("client_id") != TV_CLIENT.CLIENT_ID:
                raise LoginException("Twitch could not validate this web device session; saved browser cookies were preserved.")
            try:
                self.user_id = int(identity["user_id"])
            except (KeyError, TypeError, ValueError):
                raise LoginException("Twitch returned an invalid account identity.") from None
            self.access_token = token
            if new_login:
                self._save(token)
                self._twitch.print("Browser-free Twitch session saved. No Chromium or desktop helper is required.")
            session = await self._twitch.get_session()
            session.headers["User-Agent"] = TV_CLIENT.USER_AGENT
            self._validate_after = monotonic() + 3600
            self._logged_in.set()
            self._twitch.gui.login.update("Logged in (browser-free device session)", self.user_id)
            if revoked:
                self._twitch.change_state(State.INVENTORY_FETCH)
            return
