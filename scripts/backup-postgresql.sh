#!/bin/bash
#
# PostgreSQL Backup Script
# Dumps PostgreSQL database and uploads to S3
#
# Usage: ./backup-postgresql.sh [namespace]
#

set -euo pipefail

# Configuration
NAMESPACE="${1:-devops-monitor}"
POD_NAME="postgres-0"
DB_NAME="devops_monitor"
DB_USER="postgres"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="devops_monitor_${BACKUP_DATE}.dump"
BACKUP_DIR="/tmp/backups"
S3_BUCKET="${S3_BUCKET:-s3://devops-monitoring-backups/postgresql}"
RETENTION_DAYS=7

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if PostgreSQL pod is running
log_info "Checking PostgreSQL pod status..."
POD_STATUS=$(kubectl get pod "${POD_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")

if [ "${POD_STATUS}" != "Running" ]; then
    log_error "PostgreSQL pod ${POD_NAME} is not running (status: ${POD_STATUS})"
    exit 1
fi

log_info "PostgreSQL pod is running"

# Dump database
log_info "Starting database dump..."
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

if kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
    pg_dump -U "${DB_USER}" -d "${DB_NAME}" --format=custom \
    > "${BACKUP_PATH}" 2>/dev/null; then
    log_info "Database dump completed: ${BACKUP_FILE}"
else
    log_error "Database dump failed"
    exit 1
fi

# Compress backup
log_info "Compressing backup..."
gzip "${BACKUP_PATH}"
BACKUP_FILE="${BACKUP_FILE}.gz"
BACKUP_PATH="${BACKUP_PATH}.gz"

# Get backup size
BACKUP_SIZE=$(du -h "${BACKUP_PATH}" | cut -f1)
log_info "Backup size: ${BACKUP_SIZE}"

# Upload to S3
if command -v aws &> /dev/null && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    log_info "Uploading to S3: ${S3_BUCKET}/${BACKUP_FILE}"

    if aws s3 cp "${BACKUP_PATH}" "${S3_BUCKET}/${BACKUP_FILE}"; then
        log_info "Upload successful"
    else
        log_error "Upload to S3 failed"
        # Keep local copy if upload fails
        log_warn "Local backup available at: ${BACKUP_PATH}"
        exit 1
    fi
else
    log_warn "AWS CLI not configured, skipping S3 upload"
    log_warn "Local backup available at: ${BACKUP_PATH}"
    exit 0
fi

# Cleanup old backups
log_info "Cleaning up old backups (retention: ${RETENTION_DAYS} days)..."

CUTOFF_DATE=$(date -d "${RETENTION_DAYS} days ago" +%Y%m%d)

if command -v aws &> /dev/null && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    # List and delete old backups from S3
    aws s3 ls "${S3_BUCKET}/" | while read -r line; do
        FILE_DATE=$(echo "$line" | awk '{print $2}' | grep -oP '\d{8}' | head -1)

        if [ "${FILE_DATE:-}" != "" ] && [ "${FILE_DATE}" -lt "${CUTOFF_DATE}" ]; then
            FILE_NAME=$(echo "$line" | awk '{print $4}')
            log_info "Deleting old backup: ${FILE_NAME}"
            aws s3 rm "${S3_BUCKET}/${FILE_NAME}"
        fi
    done
fi

# Cleanup local backups
find "${BACKUP_DIR}" -name "devops_monitor_*.dump.gz" -mtime +${RETENTION_DAYS} -delete

# Cleanup current backup
rm -f "${BACKUP_PATH}"

log_info "Backup completed successfully: ${BACKUP_FILE}"
exit 0
