import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.models.alerts import AlertRule

router = APIRouter(prefix="/alerts", tags=["alerts"])

RULES_FILE = "data/alert_rules.json"


def _load_rules() -> list[dict]:
    if not os.path.exists(RULES_FILE):
        return []
    with open(RULES_FILE) as f:
        return json.load(f)


def _save_rules(rules: list[dict]):
    os.makedirs(os.path.dirname(RULES_FILE), exist_ok=True)
    with open(RULES_FILE, "w") as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)


@router.get("/rules", response_model=list[AlertRule])
async def list_rules():
    return _load_rules()


@router.post("/rules", response_model=AlertRule, status_code=201)
async def create_rule(rule: AlertRule):
    rules = _load_rules()
    rule.id = str(uuid.uuid4())
    rules.append(rule.model_dump())
    _save_rules(rules)
    return rule


@router.put("/rules/{rule_id}", response_model=AlertRule)
async def update_rule(rule_id: str, rule_update: AlertRule):
    rules = _load_rules()
    for i, r in enumerate(rules):
        if r["id"] == rule_id:
            rule_update.id = rule_id
            rules[i] = rule_update.model_dump()
            _save_rules(rules)
            return rule_update
    raise HTTPException(status_code=404, detail="Rule not found")


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: str):
    rules = _load_rules()
    rules = [r for r in rules if r["id"] != rule_id]
    _save_rules(rules)


@router.get("/history")
async def get_history():
    history_file = "data/alert_history.json"
    if not os.path.exists(history_file):
        return []
    with open(history_file) as f:
        return json.load(f)
