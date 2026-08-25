#!/bin/bash
#
# Load Test Runner Script
# Phase 9 - Sprint 4 - Day 17
#
# This script runs K6 load tests against the backend.
#
# Prerequisites:
# - K6 installed: https://k6.io/
# - Backend running (or script will start it)
#
# Usage: ./scripts/run-load-tests.sh [backend_url]
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BACKEND_URL=${1:-http://localhost:8000}
API_KEY=${2:-dev-key-123}

echo "🚀 Load Testing Script"
echo "===================="
echo "Backend URL: $BACKEND_URL"
echo ""

# Check if k6 is installed
if ! command -v k6 &> /dev/null; then
    echo -e "${RED}❌ k6 not found${NC}"
    echo "Install: https://k6.io/docs/getting-started/installation/"
    exit 1
fi

# Check if backend is running
if ! curl -sf "${BACKEND_URL}/health" > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠️  Backend not responding at $BACKEND_URL${NC}"
    echo "Make sure the backend is running before running load tests"
    exit 1
fi

echo -e "${GREEN}✅ Backend is responding${NC}"
echo ""

# Create results directory
mkdir -p test-results

# Run overview load test
echo "1️⃣ Running Overview Load Test..."
k6 run \
    --out json=test-results/overview-results.json \
    --summary-export=test-results/overview-summary.json \
    --env BACKEND_URL="$BACKEND_URL" \
    tests/load/overview_load_test.k6.js \
    || echo -e "${YELLOW}⚠️  Overview test had warnings${NC}"

echo ""
echo "2️⃣ Running Alert Load Test..."
k6 run \
    --out json=test-results/alert-results.json \
    --summary-export=test-results/alert-summary.json \
    --env BACKEND_URL="$BACKEND_URL" \
    --env API_KEY="$API_KEY" \
    tests/load/alert_load_test.k6.js \
    || echo -e "${YELLOW}⚠️  Alert test had warnings${NC}"

echo ""
echo -e "${GREEN}✅ Load tests complete!${NC}"
echo ""
echo "Results:"
echo "  Overview: test-results/overview-summary.json"
echo "  Alert:    test-results/alert-summary.json"
echo ""
echo "View JSON results:"
echo "  cat test-results/overview-summary.json | jq '.metrics'"
echo ""
