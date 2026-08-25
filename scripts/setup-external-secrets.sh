#!/bin/bash
#
# External Secrets Operator Setup Script
# Phase 9 - Sprint 3 - Day 14
#
# This script installs and configures External Secrets Operator
# for Kubernetes secret management.
#
# Usage: ./scripts/setup-external-secrets.sh [namespace]
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

NAMESPACE=${1:-devops-monitoring}
ESO_VERSION="0.9.1"

echo "🔧 External Secrets Operator Setup"
echo "=================================="
echo "Namespace: $NAMESPACE"
echo ""

# Check kubectl
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}❌ kubectl not found${NC}"
    exit 1
fi

# Check helm
if ! command -v helm &> /dev/null; then
    echo -e "${YELLOW}⚠️  Helm not found. Installing...${NC}"
    curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

echo "1️⃣ Adding External Secrets Operator Helm repo..."
helm repo add external-secrets https://external-secrets.io/external-secrets/
helm repo update

echo ""
echo "2️⃣ Installing External Secrets Operator..."
helm upgrade --install external-secrets external-secrets/external-secrets \
    --namespace external-secrets \
    --create-namespace \
    --version $ESO_VERSION \
    --set installCRDs=true \
    --set "resources.limits.cpu=500m" \
    --set "resources.limits.memory=512Mi" \
    --set "resources.requests.cpu=100m" \
    --set "resources.requests.memory=128Mi" \
    --wait

echo ""
echo "3️⃣ Verifying installation..."
kubectl wait --for=condition=available \
    deployment/external-secrets \
    -n external-secrets \
    --timeout=60s

echo -e "${GREEN}✅ External Secrets Operator installed${NC}"

echo ""
echo "4️⃣ Creating SecretStore and ExternalSecrets..."
kubectl apply -f k8s/external-secrets/secretstore.yaml
kubectl apply -f k8s/external-secrets/external-secret.yaml

echo ""
echo "5️⃣ Verifying secrets..."
sleep 5
kubectl get externalsecret -n $NAMESPACE
kubectl get secretstore -n $NAMESPACE

echo ""
echo -e "${GREEN}✅ Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Configure your Vault/AWS/GCP credentials"
echo "  2. Create secrets in your external provider"
echo "  3. Verify secrets are synced: kubectl get secrets -n $NAMESPACE"
echo ""
echo "Example - Check synced secrets:"
echo "  kubectl get secret backend-secrets -n $NAMESPACE -o yaml"
