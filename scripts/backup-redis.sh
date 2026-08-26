#!/bin/bash
#
# Redis Backup Script
# Dumps Redis database and saves to persistent storage
#
# Usage: ./backup-redis.sh [namespace]
#

set -euo pipefail

# Configuration
NAMESPACE="${1:-devops-monitor}"
REDIS_POD_NAME="redis-0"
BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="redis_dump_${BACKUP_DATE}.rdb"
BACKUP_DIR="/tmp/backups/redis"
RETENTION_DAYS=1
RETENTION_HOURS=24

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

# Create backup directory
mkdir -p "${BACKUP_DIR}"

# Check if Redis pod is running
log_info "Checking Redis pod status..."
POD_STATUS=$(kubectl get pod "${REDIS_POD_NAME}" -n "${NAMESPACE}" -o jsonpath='{.status.phase}' 2>/dev/null || echo "")

if [ "${POD_STATUS}" != "Running" ]; then
    log_error "Redis pod ${REDIS_POD_NAME} is not running (status: ${POD_STATUS})"
    exit 1
fi

log_info "Redis pod is running"

# Trigger Redis BGSAVE
log_info "Triggering Redis background save..."
if kubectl exec "${REDIS_POD_NAME}" -n "${NAMESPACE}" -- redis-cli BGSAVE > /dev/null 2>&1; then
    log_info "BGSAVE initiated"
else
    log_error "Failed to initiate BGSAVE"
    exit 1
fi

# Wait for BGSAVE to complete
log_info "Waiting for BGSAVE to complete..."
WAIT_COUNT=0
MAX_WAIT=60

while [ ${WAIT_COUNT} -lt ${MAX_WAIT} ]; do
    SAVE_STATUS=$(kubectl exec "${REDIS_POD_NAME}" -n "${NAMESPACE}" -- \
        redis-cli LASTSAVE 2>/dev/null || echo "0")

    if [ "${SAVE_STATUS}" != "0" ]; then
        log_info "BGSAVE completed"
        break
    fi

    sleep 1
    WAIT_COUNT=$((WAIT_COUNT + 1))
done

if [ ${WAIT_COUNT} -ge ${MAX_WAIT} ]; then
    log_error "BGSAVE timeout"
    exit 1
fi

# Copy RDB file from pod
log_info "Copying RDB file..."
RDB_PATH="${BACKUP_DIR}/${BACKUP_FILE}"

if kubectl exec "${REDIS_POD_NAME}" -n "${NAMESPACE}" -- \
    cat /data/dump.rdb > "${RDB_PATH}" 2>/dev/null; then
    log_info "RDB file copied"
else
    log_error "Failed to copy RDB file"
    exit 1
fi

# Compress backup
log_info "Compressing backup..."
gzip "${RDB_PATH}"
BACKUP_FILE="${BACKUP_FILE}.gz"
RDB_PATH="${RDB_PATH}.gz"

# Get backup size
BACKUP_SIZE=$(du -h "${RDB_PATH}" | cut -f1)
log_info "Backup size: ${BACKUP_SIZE}"

# Upload to S3 if available
if command -v aws &> /dev/null && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    S3_BUCKET="${S3_BUCKET:-s3://devops-monitoring-backups/redis}"
    log_info "Uploading to S3: ${S3_BUCKET}/${BACKUP_FILE}"

    if aws s3 cp "${RDB_PATH}" "${S3_BUCKET}/${BACKUP_FILE}"; then
        log_info "Upload successful"
    else
        log_warn "Upload to S3 failed, keeping local copy"
    fi
fi

# Cleanup old local backups
log_info "Cleaning up old backups..."
find "${BACKUP_DIR}" -name "redis_dump_*.rdb.gz" -mtime +${RETENTION_DAYS} -delete

# Cleanup current backup after S3 upload (if successful)
if [ -z "${AWS_ACCESS_KEY_ID:-}" ]; then
    log_warn "No S3 configured, keeping local backup: ${RDB_PATH}"
else
    rm -f "${RDB_PATH}"
fi

log_info "Redis backup completed successfully: ${BACKUP_FILE}"
exit 0
