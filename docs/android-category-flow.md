# Android Drop Category Flow

This mirrors the desktop GUI/CLI flow. The settings category picker is not a Twitch-wide category search.

## Desktop GUI Flow

1. `Twitch.fetch_inventory()` runs during `State.INVENTORY_FETCH`.
2. It fetches current inventory with `GQL_QUERIES["Inventory"]`.
3. It fetches available drop campaigns with `GQL_QUERIES["Campaigns"]` / `ViewerDropsDashboard`.
4. It filters campaign statuses to `ACTIVE` and `UPCOMING`.
5. It fetches campaign details and merges them with inventory campaign data.
6. It builds `DropsCampaign` objects.
7. It calls `gui.set_games(set(campaign.game for campaign in self.inventory))`.
8. Settings priority/exclude values are game names from that loaded campaign inventory.
9. The miner later uses those names against `settings.priority` and `settings.exclude` to build `wanted_games`.

## Android Rule

Android must only offer categories/games from loaded drop campaigns:

- Source: `Inventory` + `ViewerDropsDashboard`.
- Scope: games from in-progress, active, or upcoming drop campaigns.
- Cache: persist the loaded game list locally for 1 hour.
- Reload: expose a manual "Reload Drop Games" action that refreshes the same cached drop-campaign list immediately.
- Typing: filter the cached loaded list locally.
- Invalid names: show a not-found warning and do not save.
- Defaults: add `Overwatch` and `Marvel Rivals` only when those names exist in the loaded drop-campaign list.
- No global Twitch category search.
- No manual freeform category save.

## Android Files

- `TwitchGql.fetchDropCategories()` loads drop-campaign games.
- `MinerCore.loadCategories()` exposes that list to UI.
- `MinerSettingsStore` persists the category cache with timestamp.
- `TDMinerApp` loads cache on startup, refreshes if older than 1 hour, and filters the cached list while typing.
