# Disaster Recovery (DR) Runbook

**Version**: 2.0 | **Environment**: Production (k8s namespace `devops-monitor`) | **Updated**: 2026-08-30

---

## Architecture: where state actually lives

The backend's **primary state is file-backed JSON** under `DATA_DIR` (env-set
to `/app/data`, backed by the `alert-data-pvc` PVC, ReadWriteOnce, mounted in
the `monitor-backend` Deployment). Redis and PostgreSQL are **optional**
add-ons, never the source of truth. All flags below default to `false`
(single replica, file-backed):

| Store | Enabled by | Role | Loss impact |
|---|---|---|---|
| `DATA_DIR` files (PVC) | always | primary state | users, rules, approvals, audit lost if PV lost |
| Redis | `ALERT_STATE_USE_REDIS` / `APPROVAL_STATE_USE_REDIS` / `ALERT_ENGINE_LEADER_LOCK` / `WS_FANOUT_USE_REDIS` = `true` | alert/approval state, locks, WS fanout | in-flight alert/approval state resets; app keeps running on files |
| PostgreSQL | `DATABASE_ENABLED=true` | mirror/analytics of file state | file state stays primary; analytics views unavailable until restored |

### Files in DATA_DIR (what you are protecting)

| File | Contents |
|---|---|
| `users.json` | local user accounts (auth) |
| `alert_rules.json` | configured alert rules |
| `alert_state.json` | alert silence/suppression state |
| `alert_history.json` | alert firing history |
| `slo_configs.json` | SLO configurations |
| `approval_state.json` | pending action approvals |
| `approval_history.json` | approval decision history |
| `audit_log.jsonl` | append-only audit trail |
| `feedback_history.json`, `registry_cache.json`, `baseline/` | secondary caches/telemetry |

---

## Backup

### 1. File state (the critical backup) — PV / `kubectl cp`

Preferred: **Velero** volume snapshots including the PVC:

```bash
velero backup create devops-monitor-daily --include-namespaces devops-monitor
velero backup describe devops-monitor-daily --details
```

Without Velero, a daily cron `kubectl cp` offsite:

```bash
POD=$(kubectl get pod -n devops-monitor -l app=monitor-backend -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n devops-monitor "$POD" -- tar czf - -C /app/data . \
  > "devops-monitor-data_$(date +%Y%m%d_%H%M%S).tar.gz"
```

Validate restoreability monthly (staging cluster or local docker-compose):

```bash
mkdir -p /tmp/dr-test && tar xzf <backup>.tar.gz -C /tmp/dr-test
python -c "import json,glob;[json.load(open(f)) for f in glob.glob('/tmp/dr-test/*.json')]"
```

### 2. PostgreSQL mirror (only if `DATABASE_ENABLED=true`)

StatefulSet `postgres`, namespace `postgres` (pod `postgres-0`):

```bash
./scripts/backup-postgresql.sh postgres    # dumps to S3 ($S3_BUCKET)
./scripts/validate-backup.sh postgres postgres
./scripts/backup-redis.sh <redis-namespace>   # only if *_USE_REDIS flags are on
```

---

## Restore procedures

### File state (DATA_DIR PV)

1. Scale down to stop writers:
   `kubectl scale deployment/monitor-backend -n devops-monitor --replicas=0`
2. Restore the PV:
   - Velero: `velero restore create --from-backup <backup-name>`
   - Manual: recreate (or keep) `alert-data-pvc`, then extract the backup
     into it from a helper pod that mounts the claim at `/data`:
     ```bash
     kubectl cp devops-monitor-data_<ts>.tar.gz restore-helper:/tmp/bak.tar.gz -n devops-monitor
     kubectl exec -n devops-monitor restore-helper -- tar xzf /tmp/bak.tar.gz -C /data
     kubectl delete pod restore-helper -n devops-monitor
     ```
3. Scale back up: `kubectl scale deployment/monitor-backend -n devops-monitor --replicas=1`
4. Verify (see below). The PVC is ReadWriteOnce — it remounts on a single node.

### PostgreSQL mirror

```bash
./scripts/restore-postgresql.sh <backup_file> postgres
```

Mirror-only loss (PV intact): just restore or even re-enable later — the
backend keeps serving from files; only mirrored/analytics data is stale.

---

## Loss scenarios

**Redis lost / flushed (redis mode on):** alert and approval *runtime* state
(silences, in-flight approvals), leader locks and WS fanout re-initialize
empty. File-backed rules/history are untouched. No restore needed; expect a
burst of re-evaluated alerts. If Redis is down for long, flip the
`*_USE_REDIS` flags back to `"false"` in `monitor-backend-config` and restart.

**PostgreSQL lost:** mirror only — nothing user-facing is lost while the
file store is primary. Restore from dump to repopulate analytics/history.

**PV / DATA_DIR lost:** the real disaster. Restore file state from the
latest backup (RPO = backup cadence). Everything else is reproducible from
the manifests in `k8s/`:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/backend/ -n devops-monitor
kubectl apply -f k8s/frontend/ -n devops-monitor
```

Secrets (`monitor-backend-secrets`) are templates — refill real values from
your secret manager (external-secrets/SOPS), never from git.

---

## Verification after any restore

```bash
kubectl rollout status deployment/monitor-backend -n devops-monitor --timeout=5m
kubectl run smoke --image=curlimages/curl:latest --rm -i --restart=Never -- \
  curl -f http://monitor-backend.devops-monitor.svc.cluster.local:8000/health
kubectl logs -n devops-monitor -l app=monitor-backend --tail=50
```

`/health` is unauthenticated (PUBLIC_PATHS). Then log in and list alert
rules / SLO configs to confirm `users.json` and rule state are back; if
`users.json` was lost, recreate the initial admin per backend docs first.
