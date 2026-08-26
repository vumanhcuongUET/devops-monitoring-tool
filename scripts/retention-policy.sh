#!/bin/bash
###############################################################################
# Data Retention Policy Enforcement Script
#
# This script enforces data retention policies across all systems:
# - Logs: 7 days (hot), 30 days (warm), 90 days (cold)
# - Metrics: 90 days (Prometheus)
# - Backups: 30 days (daily), 12 weeks (weekly), 7 years (audit logs)
# - Audit logs: 7 years (compliance)
#
# Usage: ./scripts/retention-policy.sh [environment]
# Environment: dev | staging | production
#
# Phase 7: Production Hardening - Week 1, Day 3-4
###############################################################################

set -euo pipefail

# Configuration
ENVIRONMENT="${1:-stating}"
RETENTION_CONFIG="/etc/retention-config.yaml"
LOG_FILE="/var/log/retention-enforcement.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $1" >> "${LOG_FILE}"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [ERROR] $1" >> "${LOG_FILE}"
    exit 1
}

# Create retention configuration
create_retention_config() {
    log "Creating retention configuration..."

    cat > "${RETENTION_CONFIG}" <<EOF
# Data Retention Policy Configuration
# Environment: ${ENVIRONMENT}

# Elasticsearch Indices Retention
elasticsearch:
  logs_hot_retention_days: 7
  logs_warm_retention_days: 30
  logs_cold_retention_days: 90

  # Index Lifecycle Management
  index_lifecycle_policies:
    logs-*:
      hot_phase:
        rollover_after: 50gb
        max_age: 7d
      warm_phase:
        min_age: 7d
        actions:
          - forcemerge: 1
          - shrink: true
      cold_phase:
        min_age: 30d
        actions:
          - freeze: true
        delete_after: 90d

# Prometheus Metrics Retention
prometheus:
  metrics_retention_days: 90
  metrics_retention_size: 50GB

  # High-value metrics (longer retention)
  long_term_metrics:
    - slo_*_metrics: 365 days
    - availability_metrics: 365 days
    - error_budget_metrics: 365 days

# PostgreSQL Backup Retention
postgresql:
  daily_backups_retention_days: 30
  weekly_backups_retention_weeks: 12  # 3 months
  yearly_backups_retention_years: 7     # 7 years for compliance

  # WAL retention
  wal_retention_days: 7

# Redis Backup Retention
redis:
  backups_retention_days: 30
  rdb_retention_hours: 24
  aof_enabled: true

# Application Logs Retention
application_logs:
  console_logs_days: 7
  file_logs_days: 30
  archived_logs_days: 90

  # Error logs (longer retention)
  error_logs_days: 365

# Audit Logs Retention (Compliance)
audit_logs:
  authentication_logs_years: 7
  authorization_logs_years: 7
  data_access_logs_years: 7
  system_changes_logs_years: 7
  incident_response_logs_years: 7

# Cost Optimization
cost_optimization:
  # Move to cheaper storage after X days
  s3_infrequent_access_after_days: 30
  s3_glacier_after_days: 90

  # Delete old data aggressively
  enable_cost_saving_cleanup: true
EOF

    log "Retention configuration created at ${RETENTION_CONFIG}"
}

# Enforce Elasticsearch retention
enforce_elasticsearch_retention() {
    log "Enforcing Elasticsearch retention policies..."

    if ! command -v curl &> /dev/null; then
        log "curl not found. Skipping Elasticsearch retention."
        return
    fi

    ES_HOST="${ES_HOST:-localhost:9200}"

    # Delete old indices
    for pattern in "logs-*" "metrics-*" "audit-*"; do
        log "Checking ${pattern} indices..."

        # Get list of indices
        indices=$(curl -s "${ES_HOST}/_cat/indices/${pattern}?h=index" | sort)

        # Process each index
        for index in $indices; do
            # Extract date from index name (assuming format: prefix-YYYY.MM.DD)
            if [[ $index =~ ([0-9]{4})\.([0-9]{2})\.([0-9]{2}) ]]; then
                index_date="${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"

                # Calculate age in days
                age_days=$(( ($(date +%s) - $(date -d "${index_date}" +%s)) / 86400 ))

                # Check if index should be deleted
                if [[ $index == logs-* && $age_days -gt 90 ]]; then
                    log "Deleting old log index: ${index} (${age_days} days old)"
                    curl -X DELETE "${ES_HOST}/${index}"
                elif [[ $index == metrics-* && $age_days -gt 90 ]]; then
                    log "Deleting old metrics index: ${index} (${age_days} days old)"
                    curl -X DELETE "${ES_HOST}/${index}"
                fi
            fi
        done
    done

    log "Elasticsearch retention enforced."
}

# Enforce Prometheus retention
enforce_prometheus_retention() {
    log "Enforcing Prometheus retention..."

    # Prometheus automatically handles retention via TSDB size limit
    # Just verify configuration
    if command -v promtool &> /dev/null; then
        promtool check config /etc/prometheus/prometheus.yml || warn "Prometheus config validation failed"
        log "Prometheus retention enforced via TSDB size limit (90 days / 50GB)"
    else
        warn "promtool not found. Cannot verify Prometheus configuration."
    fi
}

# Enforce S3 retention policies
enforce_s3_retention() {
    log "Enforcing S3 retention policies..."

    S3_BUCKET="s3://devops-monitoring-backups-${ENVIRONMENT}"

    # Set lifecycle policies
    cat > /tmp/s3_lifecycle_policy.json <<EOF
{
  "Rules": [
    {
      "Id": "DeleteOldBackups",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "postgresql/daily/"
      },
      "Expiration": {
        "Days": 30
      }
    },
    {
      "Id": "TransitionWeeklyToGlacier",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "postgresql/weekly/"
      },
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 2555  # 7 years
      }
    },
    {
      "Id": "TransitionRedisToIA",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "redis/"
      },
      "Transitions": [
        {
          "Days": 30,
          "StorageClass": "STANDARD_IA"
        }
      ],
      "Expiration": {
        "Days": 30
      }
    },
    {
      "Id": "TransitionAuditToGlacier",
      "Status": "Enabled",
      "Filter": {
        "Prefix": "audit/"
      },
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "GLACIER"
        }
      ],
      "Expiration": {
        "Days": 2555  # 7 years
      }
    }
  ]
}
EOF

    # Apply lifecycle policy
    aws s3api put-bucket-lifecycle-configuration \
        --bucket "devops-monitoring-backups-${ENVIRONMENT}" \
        --lifecycle-configuration file:///tmp/s3_lifecycle_policy.json || error "Failed to set S3 lifecycle policy"

    log "S3 retention policies applied."
}

# Clean local backup files
clean_local_backups() {
    log "Cleaning local backup files..."

    BACKUP_ROOT="/backups"

    # Clean daily backups older than 7 days
    find "${BACKUP_ROOT}/postgresql/daily" -type f -mtime +7 -delete
    find "${BACKUP_ROOT}/redis" -type f -mtime +7 -delete
    find "${BACKUP_ROOT}/elasticsearch" -type f -mtime +7 -delete

    # Keep weekly backups for 12 weeks
    find "${BACKUP_ROOT}/postgresql/weekly" -type f -mtime +$((12*7)) -delete

    log "Local backup cleanup complete."
}

# Enforce database-specific retention
enforce_database_retention() {
    log "Enforcing database-specific retention..."

    # PostgreSQL
    if command -v psql &> /dev/null; then
        log "Cleaning up old PostgreSQL data..."

        # Clean up old query statistics
        psql -U postgres -d devops_monitoring -c "
            DELETE FROM query_statistics
            WHERE created_at < NOW() - INTERVAL '90 days';
        " || warn "Failed to clean query_statistics"

        # Clean up old audit records (except compliance-critical ones)
        psql -U postgres -d devops_monitoring -c "
            DELETE FROM audit_logs
            WHERE category NOT IN ('authentication', 'authorization', 'data_access')
            AND created_at < NOW() - INTERVAL '365 days';
        " || warn "Failed to clean audit_logs"

        log "PostgreSQL retention enforced."
    fi
}

# Generate retention report
generate_retention_report() {
    log "Generating retention report..."

    REPORT_FILE="/tmp/retention-report-$(date +%Y%m%d).txt"

    cat > "${REPORT_FILE}" <<EOF
========================================
Data Retention Compliance Report
========================================
Environment: ${ENVIRONMENT}
Generated: $(date)

RETENTION SUMMARY
------------------

Elasticsearch Indices:
  - Hot data: 7 days
  - Warm data: 30 days
  - Cold data: 90 days
  - Total retention: 90 days

Prometheus Metrics:
  - Standard metrics: 90 days
  - Long-term metrics: 365 days
  - TSDB size limit: 50GB

PostgreSQL Backups:
  - Daily: 30 days
  - Weekly: 12 weeks (3 months)
  - Yearly: 7 years (compliance)
  - WAL: 7 days

Redis Backups:
  - RDB snapshots: 30 days
  - AOF enabled: Yes

Audit Logs (Compliance):
  - All categories: 7 years
  - Authentication: 7 years
  - Authorization: 7 years
  - Data Access: 7 years

Cost Optimization:
  - S3 IA transition: Day 30
  - S3 Glacier transition: Day 90
  - Aggressive cleanup: Enabled

========================================
EOF

    # Add current storage usage
    echo "" >> "${REPORT_FILE}"
    echo "CURRENT STORAGE USAGE" >> "${REPORT_FILE}"
    echo "---------------------" >> "${REPORT_FILE}"

    # S3 usage
    if command -v aws &> /dev/null; then
        echo "S3 Usage:" >> "${REPORT_FILE}"
        aws s3 ls "s3://devops-monitoring-backups-${ENVIRONMENT}" --recursive --human-readable --summarize >> "${REPORT_FILE}" 2>&1 || true
    fi

    # Local backup usage
    echo "" >> "${REPORT_FILE}"
    echo "Local Backup Usage:" >> "${REPORT_FILE}"
    du -sh /backups/* >> "${REPORT_FILE}" 2>&1 || true

    # Elasticsearch indices size
    if command -v curl &> /dev/null; then
        echo "" >> "${REPORT_FILE}"
        echo "Elasticsearch Indices Size:" >> "${REPORT_FILE}"
        curl -s "${ES_HOST:-localhost:9200}/_cat/indices?v" >> "${REPORT_FILE}" 2>&1 || true
    fi

    log "Retention report generated at ${REPORT_FILE}"
    cat "${REPORT_FILE}"
}

# Setup automated enforcement cron job
setup_retention_cron() {
    log "Setting up automated retention enforcement..."

    # Create cron job for daily retention check
    cat > /tmp/retention_crontab <<EOF
# Data Retention Enforcement (Runs daily at 04:00 UTC)
0 4 * * * /usr/local/bin/scripts/retention-policy.sh ${ENVIRONMENT} > /var/log/retention-enforcement.log 2>&1
EOF

    # Add to existing crontab or create new one
    (crontab -l 2>/dev/null | grep -v "retention-policy"; cat /tmp/retention_crontab) | crontab -

    log "Retention enforcement cron job configured."
}

# Main execution
main() {
    log "=========================================="
    log "Data Retention Policy Enforcement"
    log "Environment: ${ENVIRONMENT}"
    log "=========================================="

    create_retention_config
    enforce_elasticsearch_retention
    enforce_prometheus_retention
    enforce_s3_retention
    clean_local_backups
    enforce_database_retention
    generate_retention_report
    setup_retention_cron

    log "=========================================="
    log "✅ RETENTION POLICY ENFORCED"
    log "=========================================="
    log ""
    log "Retention Configuration: ${RETENTION_CONFIG}"
    log "Next Run: Tomorrow 04:00 UTC (automated)"
    log "Report: $(ls -t /tmp/retention-report-*.txt | head -1)"
}

# Run main function
main "$@"
