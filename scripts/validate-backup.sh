#!/bin/bash
#
# Backup Validation Script
# Validates backup integrity by performing test restore
#
# Usage: ./validate-backup.sh [postgresql|redis] [namespace]
#

set -euo pipefail

BACKUP_TYPE="${1:-postgresql}"
NAMESPACE="${2:-postgres}"
# Discover the Postgres pod from its label — the DB runs as a Deployment in
# the `postgres` namespace, "postgres-0" never existed.
POD_NAME="${POD_NAME:-$(kubectl get pods -n "${NAMESPACE}" \
    -l app=postgres --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)}"
if [ "${BACKUP_TYPE}" = "postgresql" ] && [ -z "${POD_NAME}" ]; then
    log_error "no running pod with label app=postgres in namespace ${NAMESPACE}"
    exit 1
fi
VALIDATION_LOG="/tmp/backup_validation_${BACKUP_TYPE}.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "${VALIDATION_LOG}"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "${VALIDATION_LOG}"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "${VALIDATION_LOG}"
}

log_validation() {
    echo -e "${GREEN}[VALIDATION]${NC} $1" | tee -a "${VALIDATION_LOG}"
}

# Initialize log
echo "=== Backup Validation Started: $(date) ===" > "${VALIDATION_LOG}"

case "${BACKUP_TYPE}" in
    postgresql)
        log_info "Validating PostgreSQL backups..."

        # Get latest backup from S3. Accept BOTH artifacts: the CronJob
        # uploads uncompressed custom-format `.dump` (internally compressed),
        # the manual script uploads `.dump.gz`.
        log_info "Fetching latest backup from S3..."
        LATEST_BACKUP=$(aws s3 ls "${S3_BUCKET:-s3://devops-monitoring-backups/postgresql}/" | \
            grep -E "\.dump(\.gz)?$" | tail -1 | awk '{print $4}')

        if [ -z "${LATEST_BACKUP}" ]; then
            log_error "No backups found in S3"
            exit 1
        fi

        log_validation "Latest backup: ${LATEST_BACKUP}"

        # Download to temp location
        TEMP_BACKUP="/tmp/${LATEST_BACKUP}"
        aws s3 cp "${S3_BUCKET:-s3://devops-monitoring-backups/postgresql}/${LATEST_BACKUP}" "${TEMP_BACKUP}"

        # Validate file integrity
        log_validation "Validating file integrity..."

        if [[ "${LATEST_BACKUP}" == *.gz ]]; then
            if gunzip -t "${TEMP_BACKUP}" 2>/dev/null; then
                log_validation "File integrity check passed"
            else
                log_error "File is corrupted"
                rm -f "${TEMP_BACKUP}"
                exit 1
            fi
        else
            log_validation "Uncompressed custom-format dump (CronJob artifact)"
        fi

        # Test restore to temporary database
        log_validation "Performing test restore..."

        TEMP_DB="backup_validation_$(date +%s)"
        kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
            psql -U postgres -c "CREATE DATABASE ${TEMP_DB};" || {
            log_error "Failed to create test database"
            rm -f "${TEMP_BACKUP}"
            exit 1
        }

        # gz artifact: stream through gunzip. Plain .dump: feed directly.
        # (A pipe held in a variable expands as literal args, never as a
        # pipeline — which is why the previous RESTORE_CMD indirection could
        # not work.)
        if [[ "${LATEST_BACKUP}" == *.gz ]]; then
            gunzip -c "${TEMP_BACKUP}" | kubectl exec -i "${POD_NAME}" -n "${NAMESPACE}" -- \
                pg_restore -U postgres -d "${TEMP_DB}" --format=custom || {
                log_error "Test restore failed"
                kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
                    psql -U postgres -c "DROP DATABASE ${TEMP_DB};"
                rm -f "${TEMP_BACKUP}"
                exit 1
            }
        else
            cat "${TEMP_BACKUP}" | kubectl exec -i "${POD_NAME}" -n "${NAMESPACE}" -- \
                pg_restore -U postgres -d "${TEMP_DB}" --format=custom || {
                log_error "Test restore failed"
                kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
                    psql -U postgres -c "DROP DATABASE ${TEMP_DB};"
                rm -f "${TEMP_BACKUP}"
                exit 1
            }
        fi

        # Verify data
        TABLE_COUNT=$(kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
            psql -U postgres -d "${TEMP_DB}" -tAc "SELECT COUNT(*) FROM information_schema.tables;")

        log_validation "Test restore successful: ${TABLE_COUNT} tables found"

        # Cleanup
        kubectl exec "${POD_NAME}" -n "${NAMESPACE}" -- \
            psql -U postgres -c "DROP DATABASE ${TEMP_DB};"
        rm -f "${TEMP_BACKUP}"

        log_validation "PostgreSQL backup validation completed"
        ;;

    redis)
        log_info "Validating Redis backups..."

        # Get latest backup from S3
        log_info "Fetching latest backup from S3..."
        LATEST_BACKUP=$(aws s3 ls "${S3_BUCKET:-s3://devops-monitoring-backups/redis}/" | \
            grep "\.rdb\.gz$" | tail -1 | awk '{print $4}')

        if [ -z "${LATEST_BACKUP}" ]; then
            log_error "No backups found in S3"
            exit 1
        fi

        log_validation "Latest backup: ${LATEST_BACKUP}"

        # Download to temp location
        TEMP_BACKUP="/tmp/${LATEST_BACKUP}"
        aws s3 cp "${S3_BUCKET:-s3://devops-monitoring-backups/redis}/${LATEST_BACKUP}" "${TEMP_BACKUP}"

        # Validate file integrity
        log_validation "Validating file integrity..."

        if gunzip -t "${TEMP_BACKUP}" 2>/dev/null; then
            log_validation "File integrity check passed"
        else
            log_error "File is corrupted"
            rm -f "${TEMP_BACKUP}"
            exit 1
        fi

        # Use redis-check-rdb if available
        log_validation "Checking RDB file format..."

        gunzip -c "${TEMP_BACKUP}" > "/tmp/temp.rdb"

        if command -v redis-check-rdb &> /dev/null; then
            if redis-check-rdb "/tmp/temp.rdb" 2>&1 | grep -q "Checksum OK"; then
                log_validation "RDB format check passed"
            else
                log_error "RDB format check failed"
                rm -f "${TEMP_BACKUP}" "/tmp/temp.rdb"
                exit 1
            fi
        else
            log_warn "redis-check-rdb not available, skipping format check"
        fi

        rm -f "${TEMP_BACKUP}" "/tmp/temp.rdb"

        log_validation "Redis backup validation completed"
        ;;

    *)
        log_error "Unknown backup type: ${BACKUP_TYPE}"
        log_info "Supported types: postgresql, redis"
        exit 1
        ;;
esac

log_validation "=== Backup Validation Completed: $(date) ==="
exit 0
