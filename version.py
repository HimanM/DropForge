__version__ = "20.6.0-beta.1.Opinionated_By_HimanM"
__prerelease__ = True
__release_message__ = """**DropForge 20.6 beta 1 - Browser-free Linux Web UI**

- Adds web-only Twitch device activation: sign in using a phone or desktop browser; the server needs no Chromium or continuously connected desktop helper.
- Preserves existing browser logins. New web installations default to device login; existing users can select Device login in Settings > Security. Browser-token import remains available and may require Chromium.
- Retries temporary authorization/network failures without deleting saved credentials. Actual Twitch revocation requires a new activation; unlimited session lifetime or automatic token renewal is not guaranteed.
- Adds persistent web authentication warnings and optional Discord authentication/recovery alerts without exposing tokens or activation codes.
- Fixes Discord completion notifications for auto-farmed free badges outside priority categories. Reward messages display reward art with direct image links; subscription badges remain excluded from automatic farming.
- Adds a free watch-time badge browser, sectioned settings, and searchable/categorized newest-first logs.
- Adds an opt-in skip-unfinishable-drops setting to GUI, TUI, CLI and web. It compares each reward's remaining watch time with its effective deadline and moves on without blocking completed claims; it is off by default.
- Keeps accepted-but-unconfirmed claims distinct from Twitch-confirmed delivery, with persistent claim receipts to suppress repeated submissions.
- Installs the Linux Web UI as a systemd service with journal logs and preserves settings, web credentials and Twitch sessions during updates. Desktop GUI, TUI and CLI authentication behavior is unchanged.

This is a beta. Browser-free mining has been tested on a low-memory Linux server, but month-long stability and every linked-account delivery case have not been verified. Treat Twitch tokens like passwords and run only one miner per Twitch account."""
