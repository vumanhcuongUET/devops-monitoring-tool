#!/bin/bash
# Phase 12 manual smoke — live stack, isolated DATA_DIR/CONFIG, fake kubectl.
set -e
SMOKE=/tmp/phase12-smoke
BACKEND=/home/vmcuong/Downloads/devops-monitoring-tool/backend
REPO=/home/vmcuong/Downloads/devops-monitoring-tool
rm -rf "$SMOKE"; mkdir -p "$SMOKE/bin" "$SMOKE/data"

# Fake kubectl on PATH: logs every real invocation to a sentinel file.
cat > "$SMOKE/bin/kubectl" <<'EOF'
#!/bin/bash
echo "kubectl $*" >> /tmp/phase12-smoke/kubectl-calls.log
echo '{"kind":"List","apiVersion":"v1","items":[]}'
EOF
chmod +x "$SMOKE/bin/kubectl"

# Staging kubeconfig stub — env_aware_executor only checks presence/readability
# outside a cluster before invoking the binary (our fake kubectl on PATH).
if [ ! -e "$HOME/.kube/config-staging" ]; then
  mkdir -p "$HOME/.kube"
  cat > "$HOME/.kube/config-staging" <<'EOF'
apiVersion: v1
kind: Config
clusters:
- name: staging-cluster
  cluster: {server: "https://127.0.0.1:6443"}
contexts:
- name: staging-cluster
  context: {cluster: staging-cluster, user: smoke}
current-context: staging-cluster
users:
- name: smoke
  user: {token: smoke}
EOF
  echo "smoke-wrote-kubeconfig" >> "$SMOKE/created-files.txt"
fi

# Registry loads from backend/projects/ (cache-first at backend/data/registry_cache.json).
cat > "$BACKEND/projects/smoke-project.yaml" <<'EOF'
name: "smoke-project"
display_name: "Smoke Project"
cluster: {name: "staging", context: "staging-cluster", region: "ap-southeast-1", platform: "kubernetes"}
namespaces: {app: "smoke", database: "smoke-db"}
owners: [{user: "smoke", email: "smoke@example.com", slack: "U1"}]
rbac:
  allowed_actions: [kubectl_get, kubectl_describe, kubectl_logs]
  requires_approval: []
  forbidden_actions: []
tags:
  environment: "staging"
EOF
rm -f "$BACKEND/data/registry_cache.json"

cd "$BACKEND"
export PATH="$SMOKE/bin:$PATH"
export DATA_DIR="$SMOKE/data"
export SLACK_SIGNING_SECRET=smoke-signing-secret

python -m app.users create alice smoke-alice-pass --role admin
python -m app.users create bob smoke-bob-pass --role operator
python -m app.users create carol smoke-carol-pass --role admin

nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8123 \
  > "$SMOKE/server.log" 2>&1 &
echo $! > "$SMOKE/server.pid"

for i in $(seq 1 40); do
  if curl -sf http://127.0.0.1:8123/health > /dev/null 2>&1; then
    echo "SERVER UP after ${i}s"; exit 0
  fi
  sleep 1
done
echo "SERVER FAILED TO START"; tail -30 "$SMOKE/server.log"; exit 1
