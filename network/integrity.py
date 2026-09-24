from __future__ import annotations

import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import aiohttp


KPSDK_SCRIPT = "https://k.twitchcdn.net/149e9513-01fa-4fb0-aad4-566afd725d1b/2d206a39-8ed7-437e-a3be-862e0f06eea3/p.js"


@contextmanager
def _temporary_profile():
    profile = tempfile.mkdtemp(prefix="dropforge-integrity-")
    try:
        yield profile
    finally:
        # Chrome can release cache files slightly after its main process exits.
        # A stale disposable profile is preferable to terminating the miner.
        shutil.rmtree(profile, ignore_errors=True)


def _stop_browser(process: subprocess.Popen) -> None:
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            if process.poll() is None:
                process.kill()
    elif process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(5)
    except subprocess.TimeoutExpired:
        if sys.platform == "win32":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGKILL)


def _browser() -> str:
    configured = os.environ.get("TDMINER_BROWSER")
    commands = [configured] if configured else []
    commands.extend(("google-chrome-stable", "google-chrome", "chromium", "chromium-browser"))
    if sys.platform == "win32":
        roots = filter(None, (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")))
        commands.extend(
            str(Path(root, relative))
            for root in roots
            for relative in (
                "Google/Chrome/Application/chrome.exe",
                "Microsoft/Edge/Application/msedge.exe",
                "BraveSoftware/Brave-Browser/Application/brave.exe",
            )
        )
    elif sys.platform == "darwin":
        commands.extend((
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ))
    for command in commands:
        if command and (resolved := shutil.which(command) or (command if Path(command).is_file() else None)):
            return resolved
    raise RuntimeError("Chrome, Chromium, Edge, or Brave is required for Twitch campaign discovery.")


async def _call(ws: aiohttp.ClientWebSocketResponse, request_id: int, method: str, params: dict | None = None) -> dict:
    await ws.send_json({"id": request_id, "method": method, "params": params or {}})
    while True:
        message = await ws.receive_json()
        if message.get("id") == request_id:
            if "error" in message:
                raise RuntimeError(message["error"].get("message", "Browser integrity request failed."))
            return message.get("result", {})


async def acquire_integrity_token(
    headers: dict[str, str], device_id: str, probe: dict | None = None
) -> tuple[str, float, str]:
    """Run Twitch's KPSDK in a disposable browser profile and return its signed proof."""
    browser = _browser()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

    with _temporary_profile() as profile:
        command = [
            browser,
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--disable-extensions",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "--mute-audio",
            "--window-position=-32000,-32000",
            "--window-size=800,600",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "about:blank",
        ]
        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            xvfb = shutil.which("xvfb-run")
            if not xvfb:
                raise RuntimeError("Xvfb is required for Twitch campaign discovery on a headless server.")
            command = [xvfb, "-a", *command]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.insert(-1, "--no-sandbox")

        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            start_new_session=sys.platform != "win32",
        )
        try:
            timeout = aiohttp.ClientTimeout(total=45)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                target = None
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError("The browser exited before Twitch integrity could start.")
                    try:
                        async with session.put(
                            f"http://127.0.0.1:{port}/json/new?{quote('about:blank', safe='')}"
                        ) as response:
                            target = await response.json()
                        break
                    except (aiohttp.ClientError, asyncio.TimeoutError):
                        await asyncio.sleep(0.1)
                if target is None:
                    raise RuntimeError("Could not connect to the temporary browser.")

                async with session.ws_connect(target["webSocketDebuggerUrl"]) as ws:
                    authorization = headers.get("Authorization", "")
                    auth_token = authorization.removeprefix("OAuth ").strip()
                    if not auth_token:
                        raise RuntimeError("A Twitch auth token is required for browser integrity.")
                    await _call(ws, 1, "Runtime.enable")
                    await _call(ws, 2, "Network.enable")
                    user_agent_result = await _call(
                        ws,
                        3,
                        "Runtime.evaluate",
                        {"expression": "navigator.userAgent", "returnByValue": True},
                    )
                    user_agent = user_agent_result.get("result", {}).get("value")
                    if not isinstance(user_agent, str) or not user_agent:
                        raise RuntimeError("Could not read the temporary browser user agent.")
                    cookie = await _call(
                        ws,
                        4,
                        "Network.setCookie",
                        {
                            "name": "auth-token",
                            "value": auth_token,
                            "domain": ".twitch.tv",
                            "path": "/",
                            "secure": True,
                        },
                    )
                    if not cookie.get("success"):
                        raise RuntimeError("Could not load the Twitch session into the temporary browser.")
                    await _call(ws, 5, "Page.enable")
                    await _call(ws, 6, "Page.navigate", {"url": "https://www.twitch.tv"})
                    await asyncio.sleep(5)
                    expression = f"""new Promise((resolve,reject)=>{{
function configure(){{window.KPSDK.configure([{{protocol:'https:',method:'POST',domain:'gql.twitch.tv',path:'/integrity'}}])}}
async function fetchIntegrity(){{const requestHeaders=Object.assign({json.dumps(headers)},{{'x-device-id':{json.dumps(device_id)}}});const response=await window.fetch('https://gql.twitch.tv/integrity',{{headers:requestHeaders,body:null,method:'POST',mode:'cors',credentials:'omit'}});if(response.status!==200)throw new Error(`Twitch integrity HTTP ${{response.status}}`);const proof=await response.json();const probe={json.dumps(probe)};if(probe!==null){{const gql=await window.fetch('https://gql.twitch.tv/gql',{{headers:Object.assign({{}},requestHeaders,{{'Client-Integrity':proof.token}}),body:JSON.stringify(probe),method:'POST',mode:'cors',credentials:'omit'}});const body=await gql.json();proof.probe={{status:gql.status,errors:(body.errors||[]).map(error=>({{message:error.message||'',code:(error.extensions||{{}}).code||''}}))}}}}return proof}}
document.addEventListener('kpsdk-load',configure,{{once:true}});document.addEventListener('kpsdk-ready',()=>fetchIntegrity().then(resolve,reject),{{once:true}});const script=document.createElement('script');script.addEventListener('error',reject);script.src={json.dumps(KPSDK_SCRIPT)};document.body.appendChild(script)
}})"""
                    result = await _call(
                        ws,
                        7,
                        "Runtime.evaluate",
                        {"expression": expression, "awaitPromise": True, "returnByValue": True, "timeout": 30000},
                    )
                    if "exceptionDetails" in result:
                        raise RuntimeError(result["exceptionDetails"].get("text", "Twitch integrity script failed."))
                    payload = result.get("result", {}).get("value", {})
                    if not isinstance(payload, dict) or not isinstance(payload.get("token"), str):
                        raise RuntimeError("Twitch integrity script returned an invalid response.")
                    browser_probe = payload.get("probe")
                    if isinstance(browser_probe, dict) and browser_probe.get("errors"):
                        errors = browser_probe["errors"]
                        if any(
                            error.get("message") == "failed integrity check"
                            or error.get("code") == "IntegrityCheckFailed"
                            for error in errors
                        ):
                            raise RuntimeError(
                                "Twitch rejected the integrity proof inside Chrome. This points to "
                                "VPS network/browser attestation, not the imported auth-token."
                            )
                        first = errors[0]
                        raise RuntimeError(
                            "Twitch's same-browser campaign probe failed: "
                            f"{first.get('code') or first.get('message') or 'unknown error'}."
                        )
                    expiration = float(payload.get("expiration", 0))
                    return (
                        payload["token"],
                        expiration / 1000 if expiration > 1e11 else expiration,
                        user_agent,
                    )
        finally:
            _stop_browser(process)
