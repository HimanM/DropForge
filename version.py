__version__ = "20.5-beta.1.Opinionated_By_HimanM"
__prerelease__ = True
__release_message__ = """**Beta notice: Twitch login changes**

Twitch retired the password-login endpoint and now applies stricter Client-Integrity checks. On some VPS or datacenter networks, a valid browser session can authenticate successfully while Twitch still blocks full campaign discovery.

**Login workaround**

1. Sign in to `https://www.twitch.tv` in a desktop browser.
2. In the browser developer tools, copy only the value of the `auth-token` cookie.
3. On a Linux Web UI installation, run `tdminer-web import-twitch-token`. The command safely stops and restarts the service while preserving settings and data.

Treat the token like a password and run only one miner per Twitch account. When Twitch blocks campaign discovery on a hosted server, this beta uses the public ttvdrops catalogue for campaign metadata only; account progress and reward claims still come directly from Twitch."""
