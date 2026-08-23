# Disaster Recovery (DR) Runbook

**Version**: 1.0
**Environment**: Production
**Last Updated**: 2026-08-23
**Owner**: SRE Team

---

## 🎯 Objective

This runbook provides step-by-step procedures for disaster recovery scenarios to ensure business continuity and minimize downtime.

---

## 📋 Recovery Objectives (RPO/RTO)

| Service | RPO (Data Loss) | RTO (Downtime) | Priority |
|----------|-----------------|----------------|----------|
| API Services | 15 min | 30 min | P0 |
| Database (PostgreSQL) | 15 min | 1 hour | P0 |
| Cache (Redis) | 1 hour | 30 min | P1 |
| Logs (Elasticsearch) | 1 day | 4 hours | P2 |
| Monitoring | 15 min | 30 min | P0 |

---

## 🚨 DR Scenarios & Procedures

### Scenario 1: Single AZ Failure

**Severity**: P1 (High)
**Frequency**: Rare (expected 1-2 times per year)
**Impact**: Partial service degradation

#### Detection
```bash
# Alert: High error rate in single AZ
# Symptoms:
# - 50% of pods showing NotReady
# - Database connection timeouts
# - Increased API latency

# Detection commands:
kubectl get nodes -L topology.kubernetes.io/zone
kubectl get pods -A | grep -i pending
kubectl top nodes
```

#### Recovery Procedure
```bash
# Step 1: Verify AZ failure (5 min)
aws ec2 describe-status --region us-east-1
kubectl get nodes -L topology.kubernetes.io/zone

# Step 2: Verify pods auto-remediated to other AZs (5 min)
kubectl get pods -A -o wide
# PDB should maintain min availability

# Step 3: Verify database failover (10 min)
# PostgreSQL should automatically failover to standby
kubectl exec -it postgres-0 -- psql -U postgres -c "SELECT pg_is_in_recovery();"

# Step 4: Verify all services operational (10 min)
kubectl get pods -A
curl -k https://api.example.com/health

# Step 5: Clear incident if all services healthy
```

**Expected Recovery Time**: 30 minutes
**Success Criteria**: All services operational in remaining AZs

---

### Scenario 2: Database Primary Failure

**Severity**: P0 (Critical)
**Frequency**: Very Rare
**Impact**: Complete service unavailability

#### Detection
```bash
# Alert: Database connection failures
# Symptoms:
# - All API requests failing
# - Database connection timeouts
# - Health checks failing

# Detection commands:
kubectl exec -it postgres-0 -- pg_isready
kubectl logs postgres-0 | tail -100
kubectl get pods -l app=postgresql
```

#### Recovery Procedure
```bash
# Step 1: Verify primary failure (5 min)
kubectl get pods -l app=postgresql
kubectl exec -it postgres-1 -- psql -U postgres -c "SELECT pg_is_in_recovery();"

# Step 2: Promote standby to primary (10 min)
kubectl exec -it postgres-1 -- psql -U postgres -c "SELECT pg_promote();"

# Step 3: Update application connection strings (5 min)
kubectl set env deployment/api-app DB_HOST=postgres-1.pgsql

# Step 4: Verify service restoration (10 min)
kubectl rollout status deployment/api-app
curl -k https://api.example.com/health

# Step 5: Recreate failed primary (ongoing)
kubectl delete pod postgres-0
# New pod will become standby

# Step 6: Update monitoring/alerting (5 min)
# Verify database metrics in Grafana
```

**Expected Recovery Time**: 35 minutes
**Success Criteria**: Database operational with minimal data loss (<15 min)

---

### Scenario 3: Complete Region Failure

**Severity**: P0 (Critical)
**Frequency**: Extremely Rare (major disaster)
**Impact**: Complete service outage

#### Detection
```bash
# Alert: Region-wide failures
# Symptoms:
# - Cannot connect to any services
# - AWS API unreachable
# - Multiple AZs affected simultaneously

# Detection: External monitoring (PagerDuty, status page)
```

#### Recovery Procedure
```bash
# Step 1: Declare DR event (immediate)
# Notify all stakeholders
# Activate war room

# Step 2: Verify region status (5 min)
aws ec2 describe-status --region us-east-1
# Check AWS Health Dashboard

# Step 3: Initiate DR region failover (15 min)
# Update DNS to point to DR region
# DR region: us-west-2

# Step 4: Activate DR infrastructure (30 min)
# - Start K8s cluster in DR region
# - Restore database from latest backup (max 15 min old)
# - Deploy application services

# Step 5: Verify service restoration (30 min)
curl -k https://dr-api.example.com/health
kubectl get pods -A

# Step 6: Switch traffic to DR region (10 min)
# Update Route53 records
# Update CDN origins

# Step 7: Monitor and stabilize (ongoing)
# Monitor metrics, logs, user reports
```

**Expected Recovery Time**: 90 minutes
**Success Criteria**: Services operational in DR region

---

### Scenario 4: Data Corruption

**Severity**: P0 (Critical)
**Frequency: Very Rare
**Impact**: Data integrity compromised

#### Detection
```bash
# Alert: Database corruption detected
# Symptoms:
# - PostgreSQL errors about corrupted pages
# - Application returning inconsistent data
# - Data validation failures

# Detection commands:
kubectl exec -it postgres-0 -- psql -U postgres -c "SELECT * FROM pg_stat_database WHERE datname = 'devops_monitoring';"
```

#### Recovery Procedure
```bash
# Step 1: Identify corruption scope (10 min)
kubectl exec -it postgres-0 -- psql -U postgres -c "VACUUM FULL VERBOSE;"
# Review logs for corruption indicators

# Step 2: Stop all writes to prevent spread (5 min)
kubectl scale deployment api-app --replicas=0

# Step 3: Determine last known good backup (5 min)
aws s3 ls s3://devops-monitoring-backups-prod/postgresql/daily/ | tail -5

# Step 4: Restore from last good backup (30 min)
./scripts/postgresql_restore.sh s3://.../backup_YYYYMMDD.dump

# Step 5: Verify data integrity (15 min)
# Run data validation scripts
# Check row counts against expected values

# Step 6: Replay WAL logs (if available) (20 min)
# Minimize data loss

# Step 7: Restore service (10 min)
kubectl scale deployment api-app --replicas=3

# Step 8: Post-incident review (ongoing)
# Document root cause
# Update prevention measures
```

**Expected Recovery Time**: 90 minutes
**Success Criteria**: Data integrity verified, services operational

---

### Scenario 5: Ransomware Attack

**Severity**: P0 (Critical)
**Frequency: Rare
**Impact: Data encrypted, ransom demand

#### Detection
```bash
# Alert: Suspicious file modifications
# Symptoms:
# - Files renamed with encrypted extensions
# - Ransom notes in directories
# - Unable to access critical files

# Detection commands:
find /backups -name "*.encrypted"
ls -la /data/ | head -20
```

#### Recovery Procedure
```bash
# Step 1: ISOLATE SYSTEMS (immediate)
# Disconnect from network
# Shut down all services
kubectl scale deployment --all --replicas=0 -A

# Step 2: Declare security incident (immediate)
# Notify security team
# Activate incident response plan

# Step 3: Assess damage (30 min)
# Identify affected systems
# Determine encryption method
# Check backup integrity

# Step 4: Verify backup safety (critical!)
# Ensure backups were not affected
aws s3 ls s3://devops-monitoring-backups-prod/ --recursive
# Check off-site backup integrity

# Step 5: Rebuild infrastructure (2-4 hours)
# Provision new K8s cluster (clean environment)
# Deploy from immutable infrastructure

# Step 6: Restore data (1-2 hours)
# Restore from verified clean backups
# Verify no ransomware in restored data

# Step 7: Security hardening (ongoing)
# Update all credentials
# Patch vulnerability
# Implement additional security measures

# Step 8: Gradual service restoration (1-2 hours)
# Bring services online one by one
# Monitor for any signs of reinfection
```

**Expected Recovery Time**: 6-10 hours
**Success Criteria**: Clean environment restored, no ransomware remnants

---

## 📞 Emergency Contacts

### Primary On-Call
| Role | Name | Contact | Hours |
|------|------|---------|-------|
| SRE Lead | [Name] | +1-XXX-XXX-XXXX | 24/7 |
| Database Lead | [Name] | +1-XXX-XXX-XXXX | Business hours |
| Security Lead | [Name] | +1-XXX-XXX-XXXX | 24/7 |

### Escalation Chain
1. **On-Call Engineer** → Immediate response
2. **SRE Lead** → 15 minutes, no response
3. **CTO/VP Engineering** → 30 minutes, no response
4. **CEO** → Critical incident only

---

## 🔔 Communication Procedures

### Internal Communication
```yaml
P0 Incident (Critical):
  Channel: #incidents-critical
  Frequency: Every 15 minutes
  Format: 
    Status: [INVESTIGATING|IDENTIFIED|MONITORING|RESOLVED]
    Impact: [affected services]
    Next Update: [time]

P1 Incident (High):
  Channel: #incidents
  Frequency: Every 30 minutes
  Format: Same as P0

P2 Incident (Medium):
  Channel: #incidents
  Frequency: Every hour
  Format: Same as P0
```

### External Communication
```yaml
Customer Communication:
  Trigger: P0 or P1 > 30 minutes
  Channel: Status page, email
  Template:
    - Incident acknowledgment (5 min)
    - Initial assessment (15 min)
    - Progress updates (hourly)
    - Resolution summary (after restoration)
```

---

## 🧪 DR Testing Procedures

### Quarterly DR Test
```yaml
Schedule: First Sunday of each quarter
Duration: 2-4 hours
Scope: Full DR failover test

Procedure:
  1. Announce maintenance window (7 days prior)
  2. Notify all stakeholders
  3. Execute failover to DR region
  4. Verify all services operational
  5. Run smoke tests
  6. Failback to primary region
  7. Document lessons learned

Success Criteria:
  ✅ RTO < 1 hour (critical services)
  ✅ RPO < 15 minutes
  ✅ Zero data corruption
  ✅ All smoke tests passing
```

### Monthly Backup Restoration Test
```yaml
Schedule: Last Friday of each month
Duration: 1 hour
Scope: Validate backup integrity

Procedure:
  1. Select random backup from last month
  2. Restore to test environment
  3. Validate data integrity
  4. Document results

Success Criteria:
  ✅ Backup restoration successful
  ✅ Data integrity verified
  ✅ No errors in restoration process
```

---

## 📊 DR Metrics & KPIs

### Key Metrics to Track
```yaml
Recovery Metrics:
  - MTTD (Mean Time To Detect)
  - MTTR (Mean Time To Resolve)
  - RPO achieved vs target
  - RTO achieved vs target
  
Test Metrics:
  - DR test success rate
  - Backup restoration success rate
  - Time to complete DR test
  
Cost Metrics:
  - DR infrastructure cost
  - Backup storage cost
  - Data transfer costs
```

### Reporting
```yaml
Weekly:
  - Backup status
  - DR infrastructure health

Monthly:
  - DR test results
  - Backup restoration test results
  - Metrics summary

Quarterly:
  - Full DR test report
  - DR procedures update
  - Cost optimization review
```

---

## 📚 Related Documentation

- [Backup Strategy](../backup-strategy.md)
- [Incident Response Runbook](../incident-response-runbook.md)
- [Maintenance Procedures](../maintenance-procedures.md)
- [Security Incident Response](../security-incident-response.md)

---

## 🔄 Change History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-08-23 | Initial document | SRE Team |

---

**Last Reviewed**: 2026-08-23
**Next Review**: 2026-11-23 (Quarterly)

**Approved By**: _________________ (SRE Lead)
**Date**: _________________
