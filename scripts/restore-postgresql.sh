#!/bin/bash
#
# PostgreSQL Restore Script
# Restores PostgreSQL database from S3 backup
#
# Usage: ./restore-postgresql.sh <backup_file> [namespace]
#

set -euo pipefail

# Configuration
BACKUP_FILE="${1}"
NAMESPACE="${2:-devops-monitor}"
POD_NAME="postgres-0"
DB_NAME="devops_monitor"
DB_USER="postgres"
BACKUP_DIR="/tmp/restores"
S3_BUCKET="${S3_BUCKET:-s3://devops-monitoring-backups/postgresql}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate input
if [ -z "${BACKUP_FILE}" ]; then
    log_error "Backup file not specified"
    log_info "Usage: $0 <backup_file> [namespace]"
    exit 1
fi

# Create restore directory
mkdir -p "${BACKUP_DIR}"

# Check if PostgreSQL pod is running
log_info "Checking PostgreSQL pod status..."
POD_STATUS=$(kubectl get pod "${POD_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")

if [ "${POD_STATUS}" != "Running" ]; then
    log_error "PostgreSQL pod ${POD_NAME} is not running (status: ${POD_STATUS})"
    exit 1
fi

log_info "PostgreSQL pod is running"

# Download backup from S3
log_info "Downloading backup from S3..."
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

if aws s3 cp "${S3_BUCKET}/${BACKUP_FILE}" "${BACKUP_PATH}"; then
    log_info "Download completed"
else
    log_error "Failed to download backup from S3"
    exit 1
fi

# Decompress if needed
if [[ "${BACKUP_FILE}" == *.gz ]]; then
    log_info "Decompressing backup..."
    gunzip "${BACKUP_PATH}"
    BACKUP_PATH="${BACKUP_PATH%.gz}"
fi

# Confirm restore
log_warn "This will restore database '${DB_NAME}' from '${BACKUP_FILE}'"
log_warn "All existing data will be lost!"
read -p "Continue? (yes/no): " CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    log_info "Restore cancelled"
    exit 0
fi

# Drop existing database
log_info "Dropping existing database..."
kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
    psql -U "${DB_USER}" -c "DROP DATABASE IF EXISTS ${DB_NAME};" 2>/dev/null || true

# Create new database
log_info "Creating new database..."
kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
    psql -U "${DB_USER}" -c "CREATE DATABASE ${DB_NAME};" || {
    log_error "Failed to create database"
    exit 1
}

# Restore database
log_info "Restoring database from backup..."
if kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
    pg_restore -U "${DB_USER}" -d "${DB_NAME}" --format=custom < "${BACKUP_PATH}"; then
    log_info "Database restore completed"
else
    log_error "Database restore failed"
    exit 1
fi

# Verify restore
log_info "Verifying restore..."
TABLE_COUNT=$(kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
    psql -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT COUNT(*) FROM information_schema.tables;" 2>/dev/null || echo "0")

if [ "${TABLE_COUNT}" -gt 0 ]; then
    log_info "Restore verified: ${TABLE_COUNT} tables found"
else
    log_error "Restore verification failed: no tables found"
    exit 1
fi

# Cleanup
rm -f "${BACKUP_PATH}"

log_info "PostgreSQL restore completed successfully"
exit 0
