#!/bin/bash
#
# Security Check Script
# Phase 9 - Sprint 3 - Day 11
#
# This script checks for potential security issues:
# 1. Secrets in git history
# 2. Unencrypted secrets in repository
# 3. Hardcoded credentials
# 4. API keys in code
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔒 Security Check Script"
echo "========================"
echo ""

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Not in a git repository${NC}"
    exit 1
fi

# 1. Check for secrets in git history
echo "1️⃣ Checking for secrets in git history..."

if command -v trufflehog &> /dev/null; then
    echo "Running TruffleHog..."
    trufflehog filesystem --directory . --json > /tmp/trufflehog-results.json 2>/dev/null || true

    if [ -s /tmp/trufflehog-results.json ]; then
        ISSUES=$(cat /tmp/trufflehog-results.json | grep -c '"source":' || echo "0")
        echo -e "${RED}❌ Found $ISSUES potential secrets in git history${NC}"
        echo "Run 'trufflehog git .' for details"
    else
        echo -e "${GREEN}✅ No secrets found in git history${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  TruffleHog not installed, skipping${NC}"
    echo "Install: pip install trufflehog"
fi

# 2. Check for .env files in git history
echo ""
echo "2️⃣ Checking for .env files in git history..."

if git log --all --full-history -- '**/.env' | grep -q .; then
    echo -e "${RED}❌ Found .env files in git history${NC}"
    echo "⚠️  Consider running: scripts/remove-env-from-history.sh"
else
    echo -e "${GREEN}✅ No .env files found in git history${NC}"
fi

# 3. Check for hardcoded secrets in current code
echo ""
echo "3️⃣ Checking for hardcoded secrets..."

# Patterns that might indicate secrets
PATTERNS=(
    "password\s*=\s*['\"].*['\"]"
    "api_key\s*=\s*['\"].*['\"]"
    "secret\s*=\s*['\"].*['\"]"
    "token\s*=\s*['\"].*['\"]"
    "ANTHROPIC_API_KEY\s*=\s*sk-ant-"
    "AKIA[0-9A-Z]{16}"  # AWS access key
    "[0-9]{34}:[0-9A-Z]{32}"  # Stripe API key pattern
)

FOUND=0
for pattern in "${PATTERNS[@]}"; do
    if grep -rI --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.yaml" --include="*.yml" "$pattern" . 2>/dev/null | grep -v "node_modules" | grep -v ".env.example" | grep -v "secrets/" | head -5 | grep -q .; then
        echo -e "${RED}❌ Potential secrets found with pattern: $pattern${NC}"
        grep -rI --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.yaml" --include="*.yml" "$pattern" . 2>/dev/null | grep -v "node_modules" | grep -v ".env.example" | grep -v "secrets/" | head -3
        FOUND=1
    fi
done

if [ $FOUND -eq 0 ]; then
    echo -e "${GREEN}✅ No hardcoded secrets found${NC}"
fi

# 4. Check .env.example is up to date
echo ""
echo "4️⃣ Checking .env.example..."

if [ -f ".env.example" ]; then
    # Count variables in .env.example
    ENV_EXAMPLE_COUNT=$(grep -c "=" .env.example || echo "0")
    echo "Found $ENV_EXAMPLE_COUNT variables in .env.example"

    # Check for common missing variables
    MISSING=()
    for var in AUTH_SECRET ANTHROPIC_API_KEY REDIS_PASSWORD; do
        if ! grep -q "$var" .env.example; then
            MISSING+=("$var")
        fi
    done

    if [ ${#MISSING[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Consider adding to .env.example: ${MISSING[*]}${NC}"
    else
        echo -e "${GREEN}✅ .env.example looks good${NC}"
    fi
else
    echo -e "${RED}❌ .env.example not found${NC}"
fi

# 5. Check for insecure file permissions
echo ""
echo "5️⃣ Checking file permissions..."

INSECURE_FILES=$(find . -type f -name "*.key" -o -name "*.pem" -o -name "*secret*" -perm /o=r 2>/dev/null | wc -l)

if [ "$INSECURE_FILES" -gt 0 ]; then
    echo -e "${RED}❌ Found $INSECURE_FILES files with world-readable permissions${NC}"
else
    echo -e "${GREEN}✅ No insecure permissions found${NC}"
fi

# Summary
echo ""
echo "========================"
echo "Security check complete!"
echo ""
echo "Recommendations:"
echo "  • Use External Secrets Operator for production secrets"
echo "  • Never commit .env files or secrets"
echo "  • Rotate any exposed credentials immediately"
echo "  • Enable branch protection rules"
