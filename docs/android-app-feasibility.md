# Android App Feasibility Report

Date: 2026-07-04

## Verdict

Building an Android app is technically feasible.

Recommended path: ship a sideload/GitHub APK only, with a native Android UI, a user-controlled Start/Stop session model, a visible foreground service, progress notifications, and a home-screen widget. Play Store distribution and multi-account support are out of scope.

## Eligibility Summary

| Area | Eligibility | Reason |
| --- | --- | --- |
| Native Android APK | Eligible | Android can run a Compose UI plus a foreground service for long-running work. |
| Reusing current Python core | Partially eligible | Current code is Python/asyncio and already runs under Termux, but packaging Python inside APK adds complexity. |
| Play Store distribution | Out of scope | The target is sideload/GitHub APK distribution only. |
| GitHub/sideload distribution | Eligible | No Play review gate. Still carries Twitch account/platform risk. |
| Single account | Eligible | Keeps token storage, UI, and service state simple. Multi-account is not planned. |
| Session-based farming | Eligible | User presses Start to run and Stop to end the foreground service. No hidden long-term autostart. |
| Home-screen widget | Eligible | Android App Widget can show status/progress and send Start/Stop intents to the app. |
| Progress notifications | Eligible | The foreground-service notification can show active campaign/drop progress and expose Stop. |
| Wake lock permission | Eligible with limits | `android.permission.WAKE_LOCK` can keep CPU work alive during an active session, but it must be released on Stop. |
| Proper mobile UI | Eligible | Existing GUI/TUI state model can guide screens, but the UI itself should be native Android, not ported Tk/Textual. |

## Current Codebase Findings

The repo is not Android-ready yet. It is a Python desktop/terminal app:

- `network/twitch.py` owns the main Twitch runtime: authenticated HTTP/GQL calls, campaign fetches, channel selection, websocket events, progress, and claiming.
- `models/inventory.py` owns campaign/drop eligibility, progress, and claim state.
- `core/settings.py` and `core/constants.py` store config, cookies, cache, and runtime paths.
- `gui/` is the desktop GUI layer.
- `tui/` is the Textual/prompt_toolkit terminal UI layer.
- `scripts/install.sh` has a Termux path that installs the Python source into a venv and writes a `tdminer` launcher.

The useful separation is that the mining logic is already mostly outside the UI. The missing Android piece is a native app shell, service lifecycle, Android storage, and secure login/token handling.

Important GUI features to preserve:

- Main status line: current watched channel/session state.
- Websocket/service health.
- Login/account status.
- Channel list with online status, game, drops flag, viewers, and manual switch.
- Campaign and drop progress as separate progress indicators.
- Output/log stream.
- Inventory images: campaign cover art and reward/badge/emote images.
- Settings parity for behavior that affects farming, especially badges/emotes support.

## Android Platform Constraints

Android will not reliably allow a silent long-running background miner. Android 8+ stops background services after an idle window unless the app is foreground-visible or uses scheduled jobs. A miner needs continuous websocket/network work, so WorkManager alone is not enough for active farming.

Required Android model:

- A foreground service while farming is active.
- Persistent notification: "Twitch Drops Miner is running".
- Notification progress bars for active campaign/drop progress.
- Stop action in the notification.
- Explicit user start/stop in the UI.
- Home-screen widget with status, current progress, and Start/Stop action.
- Partial wake lock only while a user-started farming session is active.
- No hidden autostart farming by default.
- Battery optimization guidance, because OEMs may still kill long-running apps.

For Android 14+, foreground service type declarations are required. The closest type is likely `dataSync` or `specialUse`. Since Play Store is not targeted, Play Console review requirements are not product constraints, but the Android platform foreground-service rules still apply.

Manifest-level permissions likely needed:

- `android.permission.INTERNET`
- `android.permission.FOREGROUND_SERVICE`
- `android.permission.FOREGROUND_SERVICE_DATA_SYNC` or the selected foreground-service type permission
- `android.permission.POST_NOTIFICATIONS` on Android 13+
- `android.permission.WAKE_LOCK`

Wake lock rule:

- Use a partial wake lock only after the user presses Start.
- Release it immediately on Stop, logout, service crash recovery, or session completion.
- Do not keep the screen awake; the app only needs CPU/network continuity.

Sources:

- Android background limits: https://developer.android.com/about/versions/oreo/background
- Android services overview: https://developer.android.com/develop/background-work/services
- Android 14 foreground service types: https://developer.android.com/about/versions/14/changes/fgs-types-required
- Android wake locks: https://developer.android.com/develop/background-work/background-tasks/awake/wakelock
- Android wake lock API reference: https://developer.android.com/reference/android/os/PowerManager.WakeLock
- Android progress-centric notifications: https://developer.android.com/about/versions/16/features/progress-centric-notifications

## Twitch / Policy Risk

This is the main blocker for a public Android app.

Twitch Terms of Service prohibit accessing Twitch services by robot, spider, scraper, crawler, or other automated means. The app's core purpose is automated watch/drop progress behavior, using Twitch endpoints and websocket events without an official Drops farming API. Twitch Developer docs also bind API/developer-product usage to the Developer Services Agreement, which restricts undocumented Program Materials and abusive request volume.

Practical conclusion:

- Sideload build: possible, same risk profile as the desktop tool.
- Play Store build: out of scope.
- Public marketing should avoid claims like "farm drops automatically in background".
- If distributed, include clear user-controlled operation and account-risk disclosure.

Sources:

- Twitch Terms of Service, prohibited conduct: https://legal.twitch.com/en/legal/terms-of-service/
- Twitch Developer Services Agreement: https://legal.twitch.com/legal/developer-agreement/
- Twitch Developer docs terms: https://dev.twitch.tv/docs

## Development Without Android Studio

Android Studio is useful, but not required.

Minimum local setup:

- JDK 17 or newer.
- Android SDK command-line tools.
- `platform-tools` for `adb`.
- Android SDK platform and build tools.
- Gradle wrapper checked into the Android project.

You do not need to install Kotlin manually. A Gradle Android project downloads the Kotlin/Android Gradle plugins declared by the project. You write Kotlin files, then build with the wrapper:

```powershell
.\gradlew.bat assembleDebug
```

Testing without a virtual device:

- Best option: use a real Android phone with USB debugging enabled.
- Install debug APK with `adb install -r app\build\outputs\apk\debug\app-debug.apk`.
- Use `adb logcat` for runtime logs.
- Use GitHub Actions to build APKs if the local machine is missing SDK pieces.
- Skip the emulator unless needed; emulator system images are large and slower than testing on a real phone.

Command-line-only emulator is possible with `sdkmanager`, `avdmanager`, and `emulator`, but it still requires downloading a system image. For this project, physical-device testing is the practical path.

Sources:

- Android command-line tools: https://developer.android.com/tools
- Build from command line: https://developer.android.com/build/building-cmdline
- `sdkmanager`: https://developer.android.com/tools/sdkmanager
- `avdmanager`: https://developer.android.com/tools/avdmanager
- Start emulator from command line: https://developer.android.com/studio/run/emulator-commandline
- Android SDK environment variables: https://developer.android.com/tools/variables

## Recommended Architecture

### Option A: Fastest APK, Reuse Python Core

Use a native Android app shell and embed the Python runtime.

Architecture:

- Kotlin + Jetpack Compose UI.
- Android foreground service starts/stops the miner.
- Foreground notification shows campaign/drop progress and a Stop action.
- Optional widget starts/stops the same service and mirrors status/progress.
- Partial wake lock is acquired only during active sessions.
- Embedded Python runs existing `network/`, `models/`, and `core/` logic.
- Android storage replaces current path assumptions for `cookies.jar`, `settings.json`, and cache.
- UI talks to the service through a local in-process bridge/events.

Pros:

- Reuses most current mining logic.
- Fastest route to a real APK.
- Good for sideload/internal builds.

Cons:

- Packaging Python and dependencies into APK is fragile.
- Debugging Android/Python bridge issues will be annoying.
- Python packaging remains the main technical risk.

Estimated effort: 2-4 weeks for a usable sideload MVP, assuming one developer familiar with Android.

### Option B: Native Kotlin Rewrite

Port the Twitch runtime to Kotlin.

Architecture:

- Kotlin + Jetpack Compose UI.
- Ktor/OkHttp networking.
- Kotlin coroutines for fetch loops and websocket handling.
- EncryptedSharedPreferences or Android Keystore-backed storage for tokens/cookies.
- Room/DataStore for settings and cached inventory.
- Foreground service for active farming.
- App Widget + Glance or RemoteViews for status and Start/Stop.

Pros:

- Cleaner Android lifecycle.
- Smaller runtime.
- Easier long-term maintenance on Android.
- Better UI/service integration.

Cons:

- More work.
- Must port and retest all Twitch request/eligibility behavior.
- Twitch endpoint fragility remains.

Estimated effort: 5-8 weeks for a solid MVP; longer for parity with desktop.

### Option C: WebView Wrapper

Not recommended.

It may produce a UI quickly, but it does not solve background execution, service lifecycle, token storage, or reliable drop farming. It is the shortest path to a bad app.

## Proposed Android UI

Design direction:

- Swiss minimal interface: strict grid, high contrast, restrained color, large typography, strong whitespace, and very few decorative elements.
- Preserve the desktop GUI's information model, but reshape it for mobile instead of copying the desktop layout.
- Use campaign cover art and reward/badge/emote images as first-class UI content. The TUI/CLI cannot show this well; the Android app should.
- No desktop clone. The app should feel like a native Android control panel for one account and one active farming session.
- Primary action is always obvious: Start when idle, Stop when running.

Screens:

- Dashboard: Start/Stop button, current watched channel, active campaign cover image, reward image strip, drop progress, campaign progress, remaining time, websocket/service health, wake-lock status, notification status.
- Campaigns: active/upcoming/expired filters, cover images, linked status, badge/emote support, priority/exclude controls, claim-ready state.
- Campaign detail: large game/campaign artwork, all drops with reward images, required minutes, progress, claim state, allowed channels.
- Channels: eligible online channels, game, viewer count, drops status, manual switch, ACL/allowed-channel indicator.
- Login: single-account device-code login URL/code, cookie import/export fallback if needed.
- Settings: priority mode, farm unlinked, badges/emotes, notification style, wake-lock toggle/explanation, battery optimization help, diagnostic/export controls.
- Logs: compact live log with copy/export.
- Widget: compact home-screen status with Idle/Running, current drop percentage, channel, and Start/Stop button.

The mobile app should exceed CLI/TUI functionality in these areas:

- Image-backed campaign inventory.
- Reward/badge/emote thumbnails.
- Notification progress indicators.
- Home-screen widget.
- One-tap Start/Stop.
- Clear battery/wake-lock state.
- Exportable diagnostics.

Minimum controls:

- Start farming.
- Stop farming.
- Reload inventory.
- Switch channel.
- Open/copy login URL.
- Export diagnostic bundle.

## MVP Scope

Build only this first:

1. Native Compose shell.
2. Foreground service with notification and stop action.
3. Notification progress indicators for campaign/drop progress.
4. Wake lock permission and scoped partial wake-lock lifecycle.
5. Home-screen widget with status and Start/Stop.
6. Single-account login/device-code flow.
7. Inventory/campaign list.
8. Start/stop farming.
9. Current drop progress.
10. Settings needed for current behavior: priority, exclude, farm unlinked, badges/emotes, notifications, wake lock.
11. Logs screen.

Skip initially:

- Play Store release.
- Multi-account.
- Background autostart.
- Chromecast/video playback.
- Full desktop GUI parity.

## Major Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Twitch account/platform enforcement | High | Sideload only; disclose risk; do not market as viewbotting; keep user-controlled. |
| Android kills the service | Medium | Foreground service, stop action, battery optimization guidance. |
| Excess battery drain | Medium | Use wake lock only during active sessions; release aggressively; expose Stop in UI, widget, and notification. |
| Python APK packaging instability | Medium | Use native Kotlin rewrite if APK packaging becomes the bottleneck. |
| Token/cookie handling | High | Use Android Keystore/EncryptedSharedPreferences; never store raw secrets in shared external storage. |
| Twitch endpoint changes | Medium | Keep shared request definitions and diagnostics; expect maintenance. |

## Recommendation

Build a sideload APK. Do not target Play Store. Do not add multi-account.

Use native Android UI plus either embedded Python for speed or Kotlin rewrite for durability. If the goal is a proper polished Android app, the Kotlin rewrite is the better final architecture. If the goal is to test quickly, embedded Python is acceptable as a temporary bridge.

The app should run only when the user starts a session. While running, it should show the same state in three places: the app dashboard, the foreground notification with progress indicators, and the home-screen widget. Stop must be available from all three.

Decision:

- MVP/sideload: yes, feasible.
- Production-quality Android app: feasible, moderate effort.
- Play Store app: out of scope.
