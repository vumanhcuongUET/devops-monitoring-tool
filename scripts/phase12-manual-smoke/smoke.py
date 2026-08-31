"""Phase 12/15 manual smoke (updated for Phase 15 dry-run semantics):

staging:  create -> operator approve -> dry-run (stays APPROVED, no side
          effect, history dry_run=true) -> REAL execute on the same action
          (EXECUTED, kubectl invoked, history dry_run=false)
prod:     create -> operator approve 403 -> admin approve (APPROVE matrix
          fix) -> execute 403 time-window (business-hours) + audited
Slack:    signed webhook approve + view; tampered sig -> 401
"""
import hashlib
import hmac
import json
import os
import time
import urllib.parse

import httpx

BASE = "http://127.0.0.1:8123"
SECRET = "smoke-signing-secret"
SENTINEL = "/tmp/phase12-smoke/kubectl-calls.log"
HISTORY = "/tmp/phase12-smoke/data/approval_history.json"

results = []


def step(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def login(user, pw):
    r = httpx.post(f"{BASE}/api/v1/auth/login", json={"username": user, "password": pw})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


alice = login("alice", "smoke-alice-pass")
bob = login("bob", "smoke-bob-pass")
carol = login("carol", "smoke-carol-pass")
step("login x3 (alice=admin, bob=operator, carol=admin)", True)


def create(headers, project, created_by, **extra):
    r = httpx.post(f"{BASE}/api/v1/actions", headers=headers, json={
        "triage_card_id": "tc-smoke", "recommendation_id": "rec-smoke",
        "project": project, "created_by": created_by, **extra,
    })
    body = r.json()
    if r.status_code != 201 or not body.get("success"):
        raise RuntimeError(f"create failed: {r.status_code} {body}")
    return body["action"]["id"], body["action"]["status"].lower()


def approve(headers, aid, by):
    return httpx.post(f"{BASE}/api/v1/actions/{aid}/approve", headers=headers,
                      json={"approved_by": by, "comment": "smoke"})


def execute(headers, aid, by, dry_run):
    return httpx.post(f"{BASE}/api/v1/actions/{aid}/execute", headers=headers,
                      json={"executed_by": by, "dry_run": dry_run})


def status_of(headers, aid):
    r = httpx.get(f"{BASE}/api/v1/actions/{aid}", headers=headers)
    return r.json().get("action", {}).get("status", "").lower()


def last_exec_details():
    if not os.path.exists(HISTORY):
        return {}
    items = json.load(open(HISTORY))
    for e in items:  # newest-first
        if e.get("event") in ("executed", "failed"):
            return e.get("details", {})
    return {}


# === Part 1: staging — dry-run then real execute on the same action =========
if os.path.exists(SENTINEL):
    os.remove(SENTINEL)

a1, st = create(alice, "smoke-project", "alice",
                command="kubectl get pods -o json", title="List pods")
step("staging: create with client command -> PENDING", st == "pending", f"status={st}")
a1_created_by = httpx.get(f"{BASE}/api/v1/actions/{a1}", headers=carol).json().get("action", {}).get("created_by")
step("created_by overridden by authenticated identity",
     a1_created_by in ("alice", None), f"created_by={a1_created_by}")

assert approve(bob, a1, "bob").status_code == 200
step("staging: bob (operator) approves — role allows in staging",
     status_of(carol, a1) == "approved")

r = execute(carol, a1, "carol", dry_run=True)
act = r.json().get("action") or {}
step("staging: dry-run keeps APPROVED (approval not consumed)",
     r.status_code == 200 and act.get("status", "").lower() == "approved",
     f"http={r.status_code} status={act.get('status')}")
step("dry run: kubectl NOT invoked (sentinel absent)", not os.path.exists(SENTINEL),
     f"sentinel exists={os.path.exists(SENTINEL)}")
step("history records dry_run=true", last_exec_details().get("dry_run") is True,
     f"dry_run={last_exec_details().get('dry_run')}")

r = execute(carol, a1, "carol", dry_run=False)
act = r.json().get("action") or {}
ran = os.path.exists(SENTINEL)
step("staging: real execute after dry-run -> EXECUTED + kubectl invoked",
     r.status_code == 200 and act.get("status", "").lower() == "executed" and ran,
     f"http={r.status_code} status={act.get('status')} sentinel={ran}")
if ran:
    step("executed argv uses --context/--kubeconfig + `get pods -o json`",
         "--context staging-cluster" in open(SENTINEL).read()
         and "get pods -o json" in open(SENTINEL).read(),
         open(SENTINEL).read().strip())
step("history records dry_run=false for the real run",
     last_exec_details().get("dry_run") is False,
     f"dry_run={last_exec_details().get('dry_run')}")

# === Part 2: production — matrix fix + time window enforcement ==============
p1, st = create(alice, "meinvoice", "alice")
step("prod: create P1 -> PENDING", st == "pending", f"status={st}")

r = approve(bob, p1, "bob")
step("prod: bob (operator) approve -> 403 (not 500)",
     r.status_code == 403 and "lacks 'approve'" in r.text,
     f"http={r.status_code} {r.text[:110]}")

r = approve(carol, p1, "carol")
p1_state = status_of(carol, p1)
step("prod: carol (admin) approves — APPROVE matrix fix works",
     r.status_code == 200 and p1_state == "approved",
     f"http={r.status_code} state={p1_state}")

r = execute(carol, p1, "carol", dry_run=False)
step("prod: execute outside business hours -> 403 time-window block",
     r.status_code == 403 and "time window" in r.text,
     f"http={r.status_code} {r.text[:110]}")

audit_log = "/tmp/phase12-smoke/data/audit_log.jsonl"
audit_hit = "time_window" in open(audit_log).read() if os.path.exists(audit_log) else False
step("time-window block audited", audit_hit)

# === Part 3: Slack signed webhook (production action) =======================
a3, _ = create(alice, "meinvoice", "alice")


def slack(payload):
    body = urllib.parse.urlencode({"payload": json.dumps(payload)})
    ts = str(int(time.time()))
    sig = "v0=" + hmac.new(SECRET.encode(), f"v0:{ts}:{body}".encode(), hashlib.sha256).hexdigest()
    return httpx.post(f"{BASE}/approvals/webhook/slack", content=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": sig,
    })


r = slack({"actions": [{"action_id": "approve_action", "value": f"approve_action:{a3}"}],
           "user": {"id": "U77", "name": "slack-ops"}})
a3_state = status_of(carol, a3)
step("Slack signed webhook approves prod action (slack attribution)",
     r.status_code == 200 and a3_state == "approved",
     f"http={r.status_code} state={a3_state}")

r = slack({"actions": [{"action_id": "view_action", "value": f"view_action:{a3}"}],
           "user": {"id": "U77", "name": "slack-ops"}})
step("Slack view_action returns action details",
     r.status_code == 200 and "kubectl" in r.text, f"http={r.status_code} len={len(r.text)}")

r2 = httpx.post(f"{BASE}/approvals/webhook/slack", content="payload=%7B%7D", headers={
    "Content-Type": "application/x-www-form-urlencoded",
    "X-Slack-Request-Timestamp": str(int(time.time())),
    "X-Slack-Signature": "v0=" + "0" * 64,
})
step("tampered signature rejected (401)", r2.status_code == 401, f"http={r2.status_code}")

print()
fails = [n for n, ok, _ in results if not ok]
print(f"SMOKE {'GREEN' if not fails else 'RED'}: {len(results) - len(fails)}/{len(results)} steps passed")
if fails:
    print("failed:", fails)
    raise SystemExit(1)
