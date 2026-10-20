"""Persist accepted claim receipts without presenting them as confirmed delivery."""
from __future__ import annotations

import json
from time import time

from web.auth import AuthStore


class PendingClaims:
    def __init__(self, store: AuthStore):
        self.store = store
        try:
            self.entries = json.loads(store.get_settings({"pending_claims": "{}"})["pending_claims"])
            if not isinstance(self.entries, dict):
                self.entries = {}
        except ValueError:
            self.entries = {}
        self.entries = {key: stamp for key, stamp in self.entries.items()
                        if isinstance(stamp, (int, float)) and time() - stamp < 7 * 86400}

    def _save(self) -> None:
        self.store.update_settings({"pending_claims": json.dumps(self.entries)})

    @staticmethod
    def key(drop) -> str:
        auth = drop.campaign._twitch._auth_state
        return f"{getattr(auth, 'user_id', '')}#{drop.campaign.id}#{drop.id}"

    def pending(self, drop) -> bool:
        return self.key(drop) in self.entries

    def recent(self, key: str) -> bool:
        return key in self.entries and time() - self.entries[key] < 3600

    def accepted(self, key: str) -> None:
        self.entries[key] = time()
        self._save()

    def confirmed(self, key: str) -> None:
        if key in self.entries:
            del self.entries[key]
            self._save()

    def reconcile(self, payload: dict) -> None:
        inventory = (((payload.get("data") or {}).get("currentUser") or {}).get("inventory") or {})
        changed = False
        for campaign in inventory.get("dropCampaignsInProgress") or []:
            for drop in campaign.get("timeBasedDrops") or []:
                state = drop.get("self") or {}
                key = state.get("dropInstanceID")
                if state.get("isClaimed") and key in self.entries:
                    del self.entries[key]
                    changed = True
        if changed:
            self._save()
