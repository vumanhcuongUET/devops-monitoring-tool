#!/bin/bash
#
# Remove .env from Git History Script
# Phase 9 - Sprint 3 - Day 11
#
# WARNING: This script rewrites git history!
# Only use this if you have accidentally committed .env files.
#
# Prerequisites:
# - Install git-filter-repo: pip install git-filter-repo
# - Backup your repository first!
# - Coordinate with your team before force pushing
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${RED}⚠️  WARNING: This will rewrite git history!${NC}"
echo ""
echo "This script will:"
echo "  1. Remove all .env files from git history"
echo "  2. Create a backup of your current state"
echo "  3. Force push will be required (manual step)"
echo ""
read -p "Do you want to continue? (yes/no): " -r
echo

if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Check if git-filter-repo is installed
if ! command -v git-filter-repo &> /dev/null; then
    echo -e "${YELLOW}⚠️  git-filter-repo not installed${NC}"
    echo "Install: pip install git-filter-repo"
    exit 1
fi

# Backup current state
BACKUP_DIR=".git.backup.$(date +%Y%m%d_%H%M%S)"
echo "Creating backup in $BACKUP_DIR..."
cp -r .git "$BACKUP_DIR"

# Remove .env files from history
echo "Removing .env files from history..."
git filter-repo --path .env --path .env.local --path-glob '*.env.*' --invert-paths

echo ""
echo -e "${GREEN}✅ .env files removed from history${NC}"
echo ""
echo "Next steps:"
echo "  1. Review the changes: git log --oneline"
echo "  2. Force push to remote: git push origin --force --all"
echo "  3. Notify your team to re-clone the repository"
echo ""
echo "Backup is at: $BACKUP_DIR"
echo "To restore: rm -rf .git && mv $BACKUP_DIR .git"
