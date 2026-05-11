import json
import os
from datetime import datetime, timezone
from typing import Any

STATE_FILE = "data/alert_state.json"
HISTORY_FILE = "data/alert_history.json"


class AlertStateTracker:
    def __init__(self):
        self._state: dict[str, dict[str, Any]] = {}
        self._load()

    def get(self, rule_id: str) -> dict[str, Any] | None:
        return self._state.get(rule_id)

    def set_breached(self, rule_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        if rule_id not in self._state:
            self._state[rule_id] = {
                "status": "pending",
                "first_breached_at": now,
                "fired_at": None,
                "resolved_at": None,
            }
        self._state[rule_id]["last_breached_at"] = now
        self._save()
        return self._state[rule_id]

    def set_firing(self, rule_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        self._state.setdefault(rule_id, {})
        self._state[rule_id]["status"] = "firing"
        self._state[rule_id]["fired_at"] = now
        self._save()
        return self._state[rule_id]

    def set_resolved(self, rule_id: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        if rule_id in self._state:
            self._state[rule_id]["status"] = "resolved"
            self._state[rule_id]["resolved_at"] = now
        self._save()
        return self._state.get(rule_id, {})

    @property
    def firing_count(self) -> int:
        return sum(1 for s in self._state.values() if s.get("status") == "firing")

    def all_state(self) -> dict[str, dict[str, Any]]:
        return self._state

    def _load(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE) as f:
                self._state = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(self._state, f, indent=2)


class AlertHistory:
    def __init__(self, max_entries: int = 100):
        self._max = max_entries
        self._entries: list[dict] = []
        self._load()

    def add(self, event: dict):
        self._entries.insert(0, event)
        self._entries = self._entries[: self._max]
        self._save()

    @property
    def entries(self) -> list[dict]:
        return self._entries

    def _load(self):
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE) as f:
                self._entries = json.load(f)

    def _save(self):
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w") as f:
            json.dump(self._entries, f, indent=2)
