#!/bin/bash
###############################################################################
# Vault Initialization & Configuration Script
#
# This script initializes Vault for production use:
# - Cluster initialization and unseal
# - Kubernetes authentication setup
# - Secrets engine mounts
# - Policy creation
#
# Usage: ./scripts/vault-init.sh [environment]
# Environment: dev | staging | production
#
# Phase 7: Production Hardening - Week 5, Day 24-25
###############################################################################

set -euo pipefail

# Configuration
ENVIRONMENT="${1:-staging}"
VAULT_NAMESPACE="vault"
VAULT_ADDR="https://vault.vault.svc:8200"
VAULT_HELM_RELEASE="vault"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if Vault is ready
wait_for_vault() {
    log "Waiting for Vault to be ready..."

    local max_attempts=60
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault status > /dev/null 2>&1; then
            log "Vault is ready!"
            return 0
        fi

        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done

    error "Vault did not become ready in time"
}

# Initialize Vault cluster
init_vault() {
    log "Initializing Vault cluster..."

    # Check if already initialized
    if kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault status | grep -q "Initialized: true"; then
        log "Vault already initialized"
        return 0
    fi

    # Initialize Vault (this will generate unseal keys and root token)
    log "Running vault init..."
    kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault init -key-shares=5 -key-threshold=3 > /tmp/vault-init.json

    # Parse init output
    VAULT_UNSEAL_KEYS=$(jq -r '.unseal_keys_b64[]' /tmp/vault-init.json)
    VAULT_ROOT_TOKEN=$(jq -r '.root_token' /tmp/vault-init.json)

    # Store securely (in production, this would go to secure storage)
    log "Storing unseal keys and root token..."
    chmod 600 /tmp/vault-init.json

    log "Vault initialized successfully!"
    log "⚠️  CRITICAL: Store these credentials securely!"
    log "   Unseal keys and root token are in: /tmp/vault-init.json"

    # Unseal Vault
    unseal_vault

    # Login with root token
    export VAULT_TOKEN="$VAULT_ROOT_TOKEN"
}

# Unseal Vault
unseal_vault() {
    log "Unsealing Vault..."

    if [ -z "$VAULT_UNSEAL_KEYS" ]; then
        error "VAULT_UNSEAL_KEYS not set. Cannot unseal."
    fi

    # Unseal with 3 keys (threshold)
    echo "$VAULT_UNSEAL_KEYS" | jq -r '.[]' | head -3 | while read -r key; do
        kubectl exec -n "$VAULT_NAMESPACE" vault-0 -- vault operator unseal "$key" > /dev/null
    done

    log "Vault unsealed!"
}

# Enable Kubernetes authentication
enable_k8s_auth() {
    log "Enabling Kubernetes authentication..."

    export VAULT_TOKEN="$VAULT_ROOT_TOKEN"

    # Enable Kubernetes auth method
    vault auth enable kubernetes

    # Configure Kubernetes auth
    vault write auth/kubernetes/config \
        kubernetes_host="https://kubernetes.default.svc:443" \
        kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt

    # Create role for external-secrets operator
    vault write auth/kubernetes/role/external-secrets \
        bound_service_account_names=external-secrets-controller \
        bound_service_account_namespaces=external-secrets \
        policies=external-secrets-policy \
        ttl=1h

    # Create role for backend services
    vault write auth/kubernetes/role/backend-services \
        bound_service_account_names=backend-sa \
        bound_service_account_namespaces=backend \
        policies=backend-policy \
        ttl=1h

    log "Kubernetes authentication enabled!"
}

# Enable secrets engines
enable_secrets_engines() {
    log "Enabling secrets engines..."

    export VAULT_TOKEN="$VAULT_ROOT_TOKEN"

    # Enable KV v2 secrets engine
    vault secrets enable -path=secret kv-v2

    # Enable database secrets engine (for dynamic credentials)
    vault secrets enable database

    # Configure PostgreSQL database
    vault write database/config/postgresql \
        plugin_name=postgresql-database-plugin \
        connection_url="postgresql://{{username}}:{{password}}@postgresql.postgres.svc.cluster.local:5432/devops_monitoring" \
        allowed_roles="devops-admin,readonly" \
        username="vault_admin" \
        password="CHANGE_ME_SECURE_PASSWORD"

    # Create roles
    vault write database/roles/devops-admin \
        db_name=postgresql \
        creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT ALL PRIVILEGES ON DATABASE devops_monitoring TO \"{{name}}\";" \
        revocation_statements="REVOKE ALL PRIVILEGES ON DATABASE devops_monitoring FROM \"{{name}}\"; DROP ROLE \"{{name}}\";" \
        default_ttl=3600 \
        max_ttl=86400

    vault write database/roles/readonly \
        db_name=postgresql \
        creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
        revocation_statements="REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM \"{{name}}\"; DROP ROLE \"{{name}}\";" \
        default_ttl=7200 \
        max_ttl=86400

    log "Secrets engines enabled!"
}

# Create policies
create_policies() {
    log "Creating Vault policies..."

    export VAULT_TOKEN="$VAULT_ROOT_TOKEN"

    # External Secrets policy
    vault policy write external-secrets-policy - <<EOF
# Allow reading secrets at secret/ path
path "secret/data/*" {
  capabilities = ["list", "read"]
}

# Allow reading database credentials
path "database/creds/*" {
  capabilities = ["read"]
}
EOF

    # Backend services policy
    vault policy write backend-policy - <<EOF
# Allow full access to backend secrets
path "secret/data/backend/*" {
  capabilities = ["create", "read", "update", "delete", "list"]
}

# Allow database dynamic credentials
path "database/creds/*" {
  capabilities = ["read"]
}
EOF

    # Admin policy (for platform team)
    vault policy write admin-policy - <<EOF
# Allow everything
path "*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
EOF

    log "Policies created!"
}

# Create initial secrets
create_initial_secrets() {
    log "Creating initial secrets..."

    export VAULT_TOKEN="$VAULT_ROOT_TOKEN"

    # Backend database credentials
    vault kv put secret/backend/database \
        url="postgresql://postgresql.postgres.svc.cluster.local:5432/devops_monitoring" \
        username="app_user" \
        password="$(openssl rand -base64 32)" \
        max_connections=100

    # API credentials
    vault kv put secret/backend/api \
        api_key="$(openssl rand -hex 32)" \
        api_secret="$(openssl rand -hex 32)"

    # Claude API credentials (for LLM)
    vault kv put secret/backend/claude \
        api_key="CHANGE_ME_ANTHROPIC_API_KEY" \
        model="claude-sonnet-4-20250514" \
        max_tokens=4096

    # Alert webhook credentials
    vault kv put secret/backend/alerts \
        slack_webhook_url="CHANGE_ME_SLACK_WEBHOOK_URL" \
        pagerduty_api_key="CHANGE_ME_PAGERDUTY_API_KEY"

    log "Initial secrets created!"
    log "⚠️  CRITICAL: Update the CHANGE_ME values with actual credentials!"
}

# Create audit logs
enable_audit_logging() {
    log "Enabling audit logging..."

    export VAULT_TOKEN="$VAULT_ROOT_TOKEN"

    # Enable file audit log
    vault audit enable file file_path=/vault/logs/audit.log

    # Enable syslog audit log
    vault audit enable syslog log_facility=AUTH tag=vault

    log "Audit logging enabled!"
}

# Create monitoring integration
create_monitoring_integration() {
    log "Creating monitoring integration..."

    export VAULT_TOKEN="$VAULT_ROOT_TOKEN"

    # Enable Prometheus metrics
    vault write sys/metrics/prometheus

    log "Monitoring integration created!"
}

# Generate secrets rotation policy
create_rotation_policy() {
    log "Creating secrets rotation policy document..."

    cat > /tmp/secrets-rotation-policy.md <<EOF
# Secrets Rotation Policy

**Environment**: ${ENVIRONMENT}
**Version**: 1.0
**Last Updated**: $(date +%Y-%m-%d)

---

## Rotation Schedule

### Database Credentials
- **Rotation Frequency**: Every 90 days
- **Method**: Vault dynamic credentials
- **Notification**: 7 days prior to rotation

### API Keys
- **Rotation Frequency**: Every 90 days
- **Method**: Manual rotation + Vault update
- **Notification**: 14 days prior to rotation

### TLS Certificates
- **Rotation Frequency**: Every 365 days
- **Method**: Automated via Let's Encrypt
- **Notification**: 30 days prior to expiration

### Service Account Tokens
- **Rotation Frequency**: Every 30 days
- **Method**: Kubernetes service account token rotation
- **Notification**: Automated

---

## Emergency Rotation

### If Compromise Suspected:
1. **IMMEDIATE**: Revoke all credentials
2. Generate new credentials
3. Update all deployments
4. Verify no unauthorized access

---

## Compliance Requirements

- **SOC2**: All secrets rotated at least annually
- **PCI-DSS**: Database credentials rotated every 90 days
- **GDPR**: Data access credentials logged and audited

---

## Rotation Procedure

### Database Credentials (Automatic via Vault)
\`\`\`bash
# Vault automatically rotates dynamic credentials
# Services request new credentials on restart
# No manual intervention required
\`\`\`

### API Keys (Manual)
\`\`\`bash
# 1. Generate new API key
openssl rand -hex 32 > new_api_key.txt

# 2. Update in Vault
vault kv put secret/backend/api api_key=$(cat new_api_key.txt)

# 3. Update application deployments
kubectl set env deployment/api-app API_KEY=$(vault kv get -field=api_key secret/backend/api)

# 4. Remove old key from production systems
# 5. Verify services operational
\`\`\`

---

## Notifications

Rotation notifications sent to:
- #platform-team (Slack)
- on-call@company.com (Email)
- Platform engineering manager (Email)
EOF

    log "Secrets rotation policy created at /tmp/secrets-rotation-policy.md"
}

# Main execution
main() {
    log "=========================================="
    log "Vault Initialization & Configuration"
    log "Environment: ${ENVIRONMENT}"
    log "=========================================="

    # Check prerequisites
    command -v vault >/dev/null 2>&1 || error "Vault CLI not found. Please install vault."
    command -v kubectl >/dev/null 2>&1 || error "kubectl not found. Please install kubectl."
    command -v jq >/dev/null 2>&1 || error "jq not found. Please install jq."

    # Wait for Vault to be ready
    wait_for_vault

    # Initialize Vault
    init_vault

    # Configure authentication
    enable_k8s_auth

    # Enable secrets engines
    enable_secrets_engines

    # Create policies
    create_policies

    # Create initial secrets
    create_initial_secrets

    # Enable audit logging
    enable_audit_logging

    # Create monitoring integration
    create_monitoring_integration

    # Create rotation policy
    create_rotation_policy

    log "=========================================="
    log "✅ VAULT CONFIGURATION COMPLETE"
    log "=========================================="
    log ""
    log "Vault is now configured for production use!"
    log ""
    log "IMPORTANT NEXT STEPS:"
    log "1. Securely store /tmp/vault-init.json (contains unseal keys)"
    log "2. Update CHANGE_ME values with actual credentials"
    log "3. Configure Vault UI ingress for external access"
    log "4. Set up monitoring for Vault cluster"
    log "5. Schedule quarterly secret rotation"
    log ""
    log "Vault UI: https://vault.${ENVIRONMENT}.example.com"
    log "Vault Address: ${VAULT_ADDR}"
    log ""
    log "Credentials stored securely in Vault:"
    log "  - secret/backend/database"
    log "  - secret/backend/api"
    log "  - secret/backend/claude"
    log "  - secret/backend/alerts"
}

# Run main function
main "$@"
