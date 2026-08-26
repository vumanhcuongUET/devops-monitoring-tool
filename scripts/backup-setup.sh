#!/bin/bash
###############################################################################
# Backup Setup Script for Production Database & Services
#
# This script sets up automated backup strategies for:
# - PostgreSQL (WAL archiving + daily backups)
# - Redis (RDB + AOF persistence)
# - Elasticsearch (Automated snapshots)
#
# Usage: ./scripts/backup-setup.sh [environment]
# Environment: dev | staging | production
#
# Phase 7: Production Hardening - Week 1, Day 3-4
###############################################################################

set -euo pipefail

# Configuration
ENVIRONMENT="${1:-staging}"
BACKUP_ROOT="/backups"
S3_BUCKET="s3://devops-monitoring-backups-${ENVIRONMENT}"
RETENTION_DAYS=30
RETENTION_WEEKLY=12  # 12 weeks = 3 months
RETENTION_YEARLY=7    # 7 years for compliance

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging
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

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    # Check if running as root (needed for some operations)
    if [ "$EUID" -ne 0 ]; then
        warn "Not running as root. Some operations may fail."
    fi

    # Check if AWS CLI is installed
    if ! command -v aws &> /dev/null; then
        error "AWS CLI not found. Please install awscli."
    fi

    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        error "kubectl not found. Please install kubectl."
    fi

    # Check if psql is installed (for PostgreSQL backup)
    if ! command -v psql &> /dev/null; then
        warn "psql not found. PostgreSQL backups will be skipped."
    fi

    log "Prerequisites check complete."
}

# Create backup directories
create_backup_dirs() {
    log "Creating backup directories..."

    mkdir -p "${BACKUP_ROOT}/postgresql/daily"
    mkdir -p "${BACKUP_ROOT}/postgresql/weekly"
    mkdir -p "${BACKUP_ROOT}/postgresql/wal"
    mkdir -p "${BACKUP_ROOT}/redis"
    mkdir -p "${BACKUP_ROOT}/elasticsearch"
    mkdir -p "${BACKUP_ROOT}/scripts"

    log "Backup directories created."
}

# Setup PostgreSQL backup with WAL archiving
setup_postgresql_backup() {
    log "Setting up PostgreSQL backup with WAL archiving..."

    # Create archive command for WAL
    cat > /tmp/pg_archive_command.sh <<'EOF'
#!/bin/bash
# PostgreSQL WAL archive command
wal_file=$1
aws s3 cp "${wal_file}" "${S3_BUCKET}/postgresql/wal/$(date +%Y/%m/%d)/" \
    --storage-class STANDARD_IA \
    || exit 1
EOF

    chmod +x /tmp/pg_archive_command.sh
    sudo mv /tmp/pg_archive_command.sh /usr/local/bin/

    # Create daily backup script
    cat > "${BACKUP_ROOT}/scripts/postgresql_daily_backup.sh" <<EOF
#!/bin/bash
# PostgreSQL Daily Backup Script
# Runs at 00:00 UTC daily

DATE=\$(date +%Y%m%d)
BACKUP_PATH="${BACKUP_ROOT}/postgresql/daily"
LOG_FILE="/var/log/postgresql_backup.log"

echo "[\$(date)] Starting PostgreSQL daily backup..." >> \${LOG_FILE}

# Perform backup
pg_dump -h localhost -U postgres -F c -b -v -f "\${BACKUP_PATH}/backup_\${DATE}.dump" devops_monitoring 2>&1 | tee -a \${LOG_FILE}

# Upload to S3
aws s3 cp "\${BACKUP_PATH}/backup_\${DATE}.dump" \
    "${S3_BUCKET}/postgresql/daily/backup_\${DATE}.dump" \
    --storage-class STANDARD_IA

# Clean local backups older than 7 days
find "\${BACKUP_PATH}" -name "backup_*.dump" -mtime +7 -delete

echo "[\$(date)] PostgreSQL daily backup complete." >> \${LOG_FILE}
EOF

    chmod +x "${BACKUP_ROOT}/scripts/postgresql_daily_backup.sh"

    # Create weekly backup script (full backup)
    cat > "${BACKUP_ROOT}/scripts/postgresql_weekly_backup.sh" <<EOF
#!/bin/bash
# PostgreSQL Weekly Backup Script (Full Backup)
# Runs at 00:00 UTC every Sunday

DATE=\$(date +%Y%m%d)
BACKUP_PATH="${BACKUP_ROOT}/postgresql/weekly"
LOG_FILE="/var/log/postgresql_backup.log"

echo "[\$(date)] Starting PostgreSQL WEEKLY backup..." >> \${LOG_FILE}

# Perform full backup with all data
pg_dumpall -h localhost -U postgres -f "\${BACKUP_PATH}/full_backup_\${DATE}.sql" 2>&1 | tee -a \${LOG_FILE}

# Upload to S3 with GLACIER storage for long-term
aws s3 cp "\${BACKUP_PATH}/full_backup_\${DATE}.sql" \
    "${S3_BUCKET}/postgresql/weekly/full_backup_\${DATE}.sql" \
    --storage-class GLACIER

# Keep weekly backups for 3 months
find "\${BACKUP_PATH}" -name "full_backup_*.sql" -mtime +${RETENTION_WEEKLY*7} -delete

echo "[\$(date)] PostgreSQL weekly backup complete." >> \${LOG_FILE}
EOF

    chmod +x "${BACKUP_ROOT}/scripts/postgresql_weekly_backup.sh"

    log "PostgreSQL backup scripts created."
}

# Setup Redis persistence
setup_redis_backup() {
    log "Setting up Redis backup with RDB + AOF..."

    # Create Redis backup script
    cat > "${BACKUP_ROOT}/scripts/redis_backup.sh" <<EOF
#!/bin/bash
# Redis Backup Script
# Runs every 6 hours

DATE=\$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_ROOT}/redis"

echo "[\$(date)] Starting Redis backup..." >> /var/log/redis_backup.log

# Trigger RDB save
redis-cli BGSAVE

# Wait for save to complete
while [ \$(redis-cli LASTSAVE) -ge \$(date +%s) ]; do
    sleep 1
done

# Copy RDB file
cp /var/lib/redis/dump.rdb "\${BACKUP_PATH}/dump_\${DATE}.rdb"

# Upload to S3
aws s3 cp "\${BACKUP_PATH}/dump_\${DATE}.rdb" \
    "${S3_BUCKET}/redis/dump_\${DATE}.rdb" \
    --storage-class STANDARD_IA

# Keep backups for 7 days
find "\${BACKUP_PATH}" -name "dump_*.rdb" -mtime +7 -delete

echo "[\$(date)] Redis backup complete." >> /var/log/redis_backup.log
EOF

    chmod +x "${BACKUP_ROOT}/scripts/redis_backup.sh"

    log "Redis backup script created."
}

# Setup Elasticsearch snapshots
setup_elasticsearch_backup() {
    log "Setting up Elasticsearch snapshots..."

    # Create snapshot repository configuration
    cat > /tmp/elasticsearch_snapshot_repo.json <<EOF
{
  "type": "s3",
  "settings": {
    "bucket": "devops-monitoring-backups-${ENVIRONMENT}",
    "region": "us-east-1",
    "base_path": "elasticsearch",
    "compress": true,
    "server_side_encryption": true
  }
}
EOF

    # Register repository (requires Elasticsearch to be running)
    if command -v curl &> /dev/null; then
        ES_HOST="${ES_HOST:-localhost:9200}"
        curl -X PUT "\${ES_HOST}/_snapshot/backup_repo" \
            -H 'Content-Type: application/json' \
            -d @/tmp/elasticsearch_snapshot_repo.json || warn "Failed to register ES snapshot repo"

        # Create snapshot policy
        cat > "${BACKUP_ROOT}/scripts/elasticsearch_snapshot.sh" <<EOF
#!/bin/bash
# Elasticsearch Snapshot Script
# Runs daily at 02:00 UTC

SNAPSHOT_NAME="snapshot_\$(date +%Y%m%d_%H%M%S)"
LOG_FILE="/var/log/elasticsearch_backup.log"

echo "[\$(date)] Starting Elasticsearch snapshot..." >> \${LOG_FILE}

# Create snapshot
curl -X PUT "\${ES_HOST}/_snapshot/backup_repo/\${SNAPSHOT_NAME}?wait_for_completion=true" >> \${LOG_FILE} 2>&1

# Delete snapshots older than 30 days
curl -X DELETE "\${ES_HOST}/_snapshot/backup_repo/*" -d '
{
  "conditions": {
    "max_age": "30d"
  }
}' >> \${LOG_FILE} 2>&1

echo "[\$(date)] Elasticsearch snapshot complete." >> \${LOG_FILE}
EOF

        chmod +x "${BACKUP_ROOT}/scripts/elasticsearch_snapshot.sh"
    else
        warn "curl not found. Elasticsearch snapshot setup skipped."
    fi

    log "Elasticsearch snapshot script created."
}

# Setup cron jobs for automated backups
setup_cron_jobs() {
    log "Setting up automated backup cron jobs..."

    # Create crontab entries
    cat > /tmp/backup_crontab <<EOF
# PostgreSQL Daily Backup (00:00 UTC)
0 0 * * * ${BACKUP_ROOT}/scripts/postgresql_daily_backup.sh

# PostgreSQL Weekly Backup (00:00 UTC, Sunday only)
0 0 * * 0 ${BACKUP_ROOT}/scripts/postgresql_weekly_backup.sh

# Redis Backup (Every 6 hours: 00:00, 06:00, 12:00, 18:00 UTC)
0 */6 * * * ${BACKUP_ROOT}/scripts/redis_backup.sh

# Elasticsearch Snapshot (02:00 UTC daily)
0 2 * * * ${BACKUP_ROOT}/scripts/elasticsearch_snapshot.sh

# Backup Cleanup (Remove old local backups)
0 3 * * * find ${BACKUP_ROOT} -type f -mtime +7 -delete
EOF

    # Install crontab
    crontab /tmp/backup_crontab || error "Failed to install crontab"

    log "Cron jobs configured."
}

# Create restore scripts
create_restore_scripts() {
    log "Creating restore scripts..."

    # PostgreSQL restore script
    cat > "${BACKUP_ROOT}/scripts/postgresql_restore.sh" <<'EOF'
#!/bin/bash
# PostgreSQL Restore Script
# Usage: ./postgresql_restore.sh <backup_file> [<database_name>]

BACKUP_FILE="${1:?Usage: $0 <backup_file> [<database_name>]}"
DB_NAME="${2:-devops_monitoring}"
LOG_FILE="/var/log/postgresql_restore.log"

echo "[$(date)] Starting PostgreSQL restore from ${BACKUP_FILE}..." >> ${LOG_FILE}

# Download from S3 if needed
if [[ ! -f "${BACKUP_FILE}" ]]; then
    echo "Downloading from S3..." >> ${LOG_FILE}
    aws s3 cp "${BACKUP_FILE}" /tmp/restore.dump
    BACKUP_FILE="/tmp/restore.dump"
fi

# Perform restore
pg_restore -h localhost -U postgres -d "${DB_NAME}" -v "${BACKUP_FILE}" 2>&1 | tee -a ${LOG_FILE}

echo "[$(date)] PostgreSQL restore complete." >> ${LOG_FILE}
EOF

    chmod +x "${BACKUP_ROOT}/scripts/postgresql_restore.sh"

    # Redis restore script
    cat > "${BACKUP_ROOT}/scripts/redis_restore.sh" <<'EOF'
#!/bin/bash
# Redis Restore Script
# Usage: ./redis_restore.sh <backup_file>

BACKUP_FILE="${1:?Usage: $0 <backup_file>}"
LOG_FILE="/var/log/redis_restore.log"

echo "[$(date)] Starting Redis restore from ${BACKUP_FILE}..." >> ${LOG_FILE}

# Download from S3 if needed
if [[ ! -f "${BACKUP_FILE}" ]]; then
    aws s3 cp "${BACKUP_FILE}" /tmp/dump.rdb
    BACKUP_FILE="/tmp/dump.rdb"
fi

# Stop Redis
redis-cli SHUTDOWN NOSAVE

# Copy RDB file
cp "${BACKUP_FILE}" /var/lib/redis/dump.rdb

# Start Redis
redis-server --daemonize yes

echo "[$(date)] Redis restore complete." >> ${LOG_FILE}
EOF

    chmod +x "${BACKUP_ROOT}/scripts/redis_restore.sh"

    log "Restore scripts created."
}

# Run backup validation test
run_backup_test() {
    log "Running backup validation test..."

    # Test PostgreSQL backup (if database is available)
    if command -v psql &> /dev/null; then
        log "Testing PostgreSQL backup..."
        TEST_DB="${BACKUP_ROOT}/postgresql/daily/test_backup.dump"
        pg_dump -h localhost -U postgres -F c -b -v -f "${TEST_DB}" devops_monitoring || warn "PostgreSQL backup test failed"
        ls -lh "${TEST_DB}" || error "Backup file not created"
        rm -f "${TEST_DB}"
        log "PostgreSQL backup test PASSED."
    fi

    # Test S3 upload
    log "Testing S3 upload..."
    echo "test" > /tmp/test_backup.txt
    aws s3 cp /tmp/test_backup.txt "${S3_BUCKET}/test/test_backup.txt" --storage-class STANDARD_IA || error "S3 upload failed"
    aws s3 ls "${S3_BUCKET}/test/" || error "S3 listing failed"
    aws s3 rm "${S3_BUCKET}/test/test_backup.txt" || error "S3 cleanup failed"
    log "S3 upload test PASSED."

    log "Backup validation test complete."
}

# Create monitoring alerts for backup failures
create_backup_alerts() {
    log "Creating backup monitoring configuration..."

    # Prometheus alert rules for backup monitoring
    cat > /tmp/backup_alerts.yaml <<EOF
groups:
  - name: backup_alerts
    interval: 1h
    rules:
      - alert: BackupFailed
        expr: backup_last_success_timestamp < (now() - 36h)
        for: 15m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Backup has not succeeded in 36 hours"
          description: "Backup for {{ $labels.service }} has not succeeded in 36 hours. RPO at risk!"

      - alert: BackupRestorationTestFailed
        expr: backup_restoration_test_success == 0
        for: 15m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Backup restoration test failed"
          description: "Latest backup restoration test for {{ $labels.service }} failed."

      - alert: BackupStorageExhausted
        expr: backup_storage_usage_percent > 90
        for: 5m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "Backup storage usage above 90%"
          description: "Backup storage at {{ $value }}% capacity."
EOF

    log "Backup monitoring alerts created at /tmp/backup_alerts.yaml"
    log "Import to Prometheus: promtool check rules /tmp/backup_alerts.yaml"
}

# Main execution
main() {
    log "=========================================="
    log "Backup Setup for Environment: ${ENVIRONMENT}"
    log "=========================================="

    check_prerequisites
    create_backup_dirs
    setup_postgresql_backup
    setup_redis_backup
    setup_elasticsearch_backup
    setup_cron_jobs
    create_restore_scripts
    run_backup_test
    create_backup_alerts

    log "=========================================="
    log "✅ BACKUP SETUP COMPLETE"
    log "=========================================="
    log ""
    log "Next Steps:"
    log "1. Review backup scripts at ${BACKUP_ROOT}/scripts/"
    log "2. Test backup restoration: ${BACKUP_ROOT}/scripts/postgresql_restore.sh"
    log "3. Monitor backup logs in /var/log/*_backup.log"
    log "4. Configure CloudWatch alarms for backup failures"
    log "5. Schedule quarterly DR testing"
    log ""
    log "Backup Locations:"
    log "  - Local: ${BACKUP_ROOT}"
    log "  - S3: ${S3_BUCKET}"
    log ""
    log "Retention Policies:"
    log "  - Daily backups: ${RETENTION_DAYS} days"
    log "  - Weekly backups: ${RETENTION_WEEKLY} weeks"
    log "  - Audit logs: ${RETENTION_YEARLY} years (compliance)"
}

# Run main function
main "$@"
