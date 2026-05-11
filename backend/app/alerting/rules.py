import json
import os
from pathlib import Path

import yaml

from app.models.alerts import AlertRule


RULES_FILE = "data/alert_rules.json"
DEFAULT_RULES_FILE = Path(__file__).parent / "default_rules.yaml"


def load_rules() -> list[AlertRule]:
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE) as f:
            raw = json.load(f)
        return [AlertRule(**r) for r in raw]

    return _load_defaults()


def _load_defaults() -> list[AlertRule]:
    if not DEFAULT_RULES_FILE.exists():
        return []
    with open(DEFAULT_RULES_FILE) as f:
        data = yaml.safe_load(f)
    rules = []
    for i, r in enumerate(data.get("rules", [])):
        r.setdefault("id", f"default-{i}")
        rules.append(AlertRule(**r))
    return rules


def save_rules(rules: list[AlertRule]):
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "w") as f:
        json.dump([r.model_dump() for r in rules], f, indent=2, ensure_ascii=False)
