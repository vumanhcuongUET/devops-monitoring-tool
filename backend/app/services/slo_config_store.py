"""Shared SLO config store (Phase 14).

`_load_configs` used to live in the HTTP router (app/api/v1/slo.py) and was
imported privately by the alerting reporter and two skills — domain state
owned by the API layer. This module is the canonical home; the router, the
Slack/SLO reporter, and the skills all consume it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.settings import settings

CONFIGS_FILE = str(Path(settings.DATA_DIR) / "slo_configs.json")
_DEFAULTS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "alerting", "default_slo_configs.yaml"
)


def load_configs() -> list[dict]:
    """User SLO configs, falling back to the shipped defaults."""
    if os.path.exists(CONFIGS_FILE):
        with open(CONFIGS_FILE) as f:
            return json.load(f)
    return load_defaults()


def load_defaults() -> list[dict]:
    """SLO configs shipped with the app (alerting/default_slo_configs.yaml)."""
    import yaml

    if not os.path.exists(_DEFAULTS_FILE):
        return []
    with open(_DEFAULTS_FILE) as f:
        data = yaml.safe_load(f)
    configs = []
    for i, c in enumerate(data.get("slo_configs", [])):
        c.setdefault("id", f"default-{i}")
        configs.append(c)
    return configs


def save_configs(configs: list[dict]) -> None:
    os.makedirs(os.path.dirname(CONFIGS_FILE), exist_ok=True)
    with open(CONFIGS_FILE, "w") as f:
        json.dump(configs, f, indent=2, ensure_ascii=False)
