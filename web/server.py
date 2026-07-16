from __future__ import annotations

import asyncio
import hmac
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiohttp import web
from yarl import URL

from version import __version__
from web.auth import AuthStore, PASSWORD_MIN_LENGTH, SESSION_TTL, Session
from web.controller import MinerController


SESSION_COOKIE = "tdminer_session"


class LoginLimiter:
    def __init__(self, attempts: int = 5, window: int = 15 * 60) -> None:
        self.attempts = attempts
        self.window = window
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def allowed(self, key: str) -> bool:
        failures = self._failures[key]
        cutoff = time.monotonic() - self.window
        while failures and failures[0] < cutoff:
            failures.popleft()
        return len(failures) < self.attempts

    def fail(self, key: str) -> None:
        self._failures[key].append(time.monotonic())

    def clear(self, key: str) -> None:
        self._failures.pop(key, None)


def _json_error(message: str, status: int) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _body(request: web.Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text="Invalid JSON body.") from exc
    if not isinstance(body, dict):
        raise web.HTTPBadRequest(text="JSON body must be an object.")
    return body


def _same_origin(request: web.Request) -> bool:
    origin = request.headers.get("Origin")
    return origin is None or urlsplit(origin).netloc == request.host


async def _session(request: web.Request, *, csrf: bool = False) -> Session | web.Response:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return _json_error("Authentication required.", 401)
    store: AuthStore = request.app["auth"]
    session = await asyncio.to_thread(store.get_session, token)
    if session is None:
        return _json_error("Session expired.", 401)
    if csrf and (
        not _same_origin(request)
        or not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf_token)
    ):
        return _json_error("Invalid request token.", 403)
    return session


def _remote(request: web.Request) -> str:
    return request.remote or "unknown"


def _secure_request(request: web.Request) -> bool:
    return request.secure or (
        _remote(request) in {"127.0.0.1", "::1"}
        and request.headers.get("X-Forwarded-Proto", "").lower() == "https"
    )


def _validate_game_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError(f"{name} must be a list with at most 100 games.")
    if any(not isinstance(game, str) or not game.strip() or len(game) > 100 for game in value):
        raise ValueError(f"{name} contains an invalid game name.")
    return [game.strip() for game in value]


def create_app(auth_path: Path, static_path: Path, *, auto_start: bool = True) -> web.Application:
    app = web.Application(client_max_size=64 * 1024)
    app["auth"] = AuthStore(auth_path)
    app["controller"] = MinerController()
    app["limiter"] = LoginLimiter()
    app["static_path"] = static_path.resolve()

    async def on_startup(application: web.Application) -> None:
        if auto_start:
            await application["controller"].start()

    async def on_cleanup(application: web.Application) -> None:
        await application["controller"].close()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    async def session_status(request: web.Request) -> web.Response:
        session = await _session(request)
        if isinstance(session, web.Response):
            return session
        return web.json_response(
            {
                "authenticated": True,
                "csrf_token": session.csrf_token,
                "name": "DropForge",
                "version": __version__,
                "password_min_length": PASSWORD_MIN_LENGTH,
            }
        )

    async def login(request: web.Request) -> web.Response:
        limiter: LoginLimiter = request.app["limiter"]
        key = _remote(request)
        if not _same_origin(request):
            return _json_error("Invalid request origin.", 403)
        if not limiter.allowed(key):
            return _json_error("Too many login attempts. Try again later.", 429)
        body = await _body(request)
        password = body.get("password")
        if not isinstance(password, str) or not await asyncio.to_thread(
            request.app["auth"].verify_password, password
        ):
            limiter.fail(key)
            return _json_error("Invalid password.", 401)
        limiter.clear(key)
        token, session = await asyncio.to_thread(request.app["auth"].create_session)
        response = web.json_response({"authenticated": True, "csrf_token": session.csrf_token})
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_TTL,
            httponly=True,
            secure=_secure_request(request),
            samesite="Lax",
            path="/",
        )
        return response

    async def logout(request: web.Request) -> web.Response:
        session = await _session(request, csrf=True)
        if isinstance(session, web.Response):
            return session
        token = request.cookies.get(SESSION_COOKIE, "")
        await asyncio.to_thread(request.app["auth"].delete_session, token)
        response = web.json_response({"authenticated": False})
        response.del_cookie(SESSION_COOKIE, path="/")
        return response

    async def reset_password(request: web.Request) -> web.Response:
        limiter: LoginLimiter = request.app["limiter"]
        key = f"recovery:{_remote(request)}"
        if not _same_origin(request):
            return _json_error("Invalid request origin.", 403)
        if not limiter.allowed(key):
            return _json_error("Too many recovery attempts. Try again later.", 429)
        body = await _body(request)
        recovery = body.get("recovery_code")
        password = body.get("new_password")
        if not isinstance(recovery, str) or not isinstance(password, str):
            return _json_error("Recovery code and new password are required.", 400)
        try:
            next_recovery = await asyncio.to_thread(
                request.app["auth"].reset_password, recovery, password
            )
        except ValueError as exc:
            return _json_error(str(exc), 400)
        if next_recovery is None:
            limiter.fail(key)
            return _json_error("Invalid recovery code.", 401)
        limiter.clear(key)
        return web.json_response({"recovery_code": next_recovery})

    async def change_password(request: web.Request) -> web.Response:
        session = await _session(request, csrf=True)
        if isinstance(session, web.Response):
            return session
        body = await _body(request)
        current = body.get("current_password")
        new = body.get("new_password")
        if not isinstance(current, str) or not isinstance(new, str):
            return _json_error("Current and new passwords are required.", 400)
        try:
            changed = await asyncio.to_thread(request.app["auth"].change_password, current, new)
        except ValueError as exc:
            return _json_error(str(exc), 400)
        if not changed:
            return _json_error("Current password is incorrect.", 401)
        response = web.json_response({"authenticated": False})
        response.del_cookie(SESSION_COOKIE, path="/")
        return response

    async def state(request: web.Request) -> web.Response:
        session = await _session(request)
        if isinstance(session, web.Response):
            return session
        return web.json_response(request.app["controller"].snapshot())

    async def miner_start(request: web.Request) -> web.Response:
        session = await _session(request, csrf=True)
        if isinstance(session, web.Response):
            return session
        started = await request.app["controller"].start()
        return web.json_response({"started": started})

    async def miner_stop(request: web.Request) -> web.Response:
        session = await _session(request, csrf=True)
        if isinstance(session, web.Response):
            return session
        stopped = await request.app["controller"].stop()
        return web.json_response({"stopped": stopped})

    async def miner_action(request: web.Request) -> web.Response:
        session = await _session(request, csrf=True)
        if isinstance(session, web.Response):
            return session
        manager = request.app["controller"].manager
        if manager is None or not request.app["controller"].running:
            return _json_error("Miner is not running.", 409)
        action = request.match_info["action"]
        if action == "reload":
            manager.reload()
        elif action == "invalidate-auth":
            manager.invalidate_auth()
        else:
            return _json_error("Unknown miner action.", 404)
        return web.json_response({"ok": True})

    async def select_channel(request: web.Request) -> web.Response:
        session = await _session(request, csrf=True)
        if isinstance(session, web.Response):
            return session
        manager = request.app["controller"].manager
        if manager is None or not request.app["controller"].running:
            return _json_error("Miner is not running.", 409)
        body = await _body(request)
        channel_id = body.get("channel_id")
        if not isinstance(channel_id, str) or not manager.select_channel(channel_id):
            return _json_error("Channel is no longer available.", 404)
        return web.json_response({"ok": True})

    async def update_settings(request: web.Request) -> web.Response:
        session = await _session(request, csrf=True)
        if isinstance(session, web.Response):
            return session
        manager = request.app["controller"].manager
        if manager is None:
            return _json_error("Start the miner before editing settings.", 409)
        body = await _body(request)
        try:
            clean: dict[str, Any] = {}
            if "priority" in body:
                clean["priority"] = _validate_game_list(body["priority"], "priority")
            if "exclude" in body:
                clean["exclude"] = _validate_game_list(body["exclude"], "exclude")
            if "priority_mode" in body:
                if body["priority_mode"] not in manager.PRIORITY_MODE_LABELS.values():
                    raise ValueError("Invalid priority mode.")
                clean["priority_mode"] = body["priority_mode"]
            for key in ("farm_unlinked", "enable_badges_emotes"):
                if key in body:
                    if not isinstance(body[key], bool):
                        raise ValueError(f"{key} must be true or false.")
                    clean[key] = body[key]
            if "available_drops_check" in body:
                if not isinstance(body["available_drops_check"], bool):
                    raise ValueError("available_drops_check must be true or false.")
                clean["available_drops_check"] = body["available_drops_check"]
            if "connection_quality" in body:
                quality = body["connection_quality"]
                if not isinstance(quality, int) or not 1 <= quality <= 6:
                    raise ValueError("Connection quality must be between 1 and 6.")
                clean["connection_quality"] = quality
            if "language" in body:
                if body["language"] not in manager.snapshot()["settings"]["languages"]:
                    raise ValueError("Unknown language.")
                clean["language"] = body["language"]
            if "proxy" in body:
                if not isinstance(body["proxy"], str) or len(body["proxy"]) > 500:
                    raise ValueError("Invalid proxy URL.")
                proxy = URL(body["proxy"])
                if proxy and proxy.scheme not in {"http", "https"}:
                    raise ValueError("Proxy URL must use http or https.")
                clean["proxy"] = body["proxy"]
            if not clean:
                raise ValueError("No supported settings were provided.")
            manager.update_settings(clean)
        except ValueError as exc:
            return _json_error(str(exc), 400)
        return web.json_response({"ok": True, "settings": manager.snapshot()["settings"]})

    async def frontend(request: web.Request) -> web.StreamResponse:
        static_root: Path = request.app["static_path"]
        tail = request.match_info.get("tail", "")
        candidate = (static_root / tail).resolve()
        if candidate.is_relative_to(static_root) and candidate.is_file():
            response = web.FileResponse(candidate)
            if "assets" in candidate.parts:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            return response
        index = static_root / "index.html"
        if not index.is_file():
            return _json_error("Web UI has not been built.", 503)
        return web.FileResponse(index)

    app.router.add_get("/api/session", session_status)
    app.router.add_post("/api/login", login)
    app.router.add_post("/api/logout", logout)
    app.router.add_post("/api/password/reset", reset_password)
    app.router.add_post("/api/password/change", change_password)
    app.router.add_get("/api/state", state)
    app.router.add_post("/api/miner/start", miner_start)
    app.router.add_post("/api/miner/stop", miner_stop)
    app.router.add_post("/api/miner/{action}", miner_action)
    app.router.add_post("/api/channels/select", select_channel)
    app.router.add_put("/api/settings", update_settings)
    app.router.add_get("/{tail:.*}", frontend)

    @web.middleware
    async def security_headers(request: web.Request, handler: Any) -> web.StreamResponse:
        response = await handler(request)
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    app.middlewares.append(security_headers)
    return app
