# On-Call Procedures

## Overview

This document defines on-call procedures for the DevOps Monitor platform, including escalation paths, handoff procedures, and incident management.

## On-Call Schedule

### Rotation
- **Weekly rotation** starting Monday 00:00 UTC
- **Primary on-call** is first responder
- **Secondary on-call** provides backup

### Schedule
```
Week 1: Primary: Alice, Backup: Bob
Week 2: Primary: Bob, Backup: Carol
Week 3: Primary: Carol, Backup: Dave
Week 4: Primary: Dave, Backup: Alice
```

## Alert Routing

### Severity Levels

| Severity | Name | Response Time | Escalation |
|----------|------|---------------|------------|
| P0 | Critical | 15 minutes | Immediate escalation to secondary |
| P1 | High | 1 hour | Escalate after 30 minutes |
| P2 | Medium | 4 hours | Escalate next business day |
| P3 | Low | Next business day | No escalation |

### Notification Channels

| Severity | Slack | PagerDuty | SMS | Call |
|----------|-------|------------|-----|------|
| P0 | ✓ | ✓ | ✓ | ✓ |
| P1 | ✓ | ✓ | ✓ | - |
| P2 | ✓ | - | - | - |
| P3 | ✓ | - | - | - |

### Slack Channels

- `#incidents-critical` - P0 incidents
- `#alerts` - P1, P2 alerts
- `#ops-notifications` - P3, informational

## Incident Response

### 1. Acknowledge Alert (5 min)

```bash
# Acknowledge in Alertmanager
curl -X POST http://alertmanager:9093/api/v1/silences \
  -d '{
    "matchers": [{"name": "alertname", "value": "HighErrorRate"}],
    "startsAt": "2026-08-26T10:00:00Z",
    "duration": "1h",
    "comment": "Investigating",
    "createdBy": "on-call-username"
  }'
```

### 2. Initial Assessment (10 min)

- Identify affected services
- Check dashboards
- Determine severity

### 3. Investigation (30 min)

- Follow relevant runbook
- Document findings
- Identify root cause

### 4. Resolution (variable)

- Execute fix
- Verify resolution
- Monitor for recurrence

### 5. Post-Incident (next business day)

- Write incident report
- Schedule postmortem
- Update runbooks

## Escalation Paths

### Technical Escalation

1. **Primary on-call** (15 min response time)
2. **Secondary on-call** (if primary unavailable)
3. **Engineering Lead** (after 1 hour)
4. **CTO** (critical issues only)

### Management Escalation

For incidents with customer impact:

1. **On-Call Engineer** - First responder
2. **Engineering Manager** - For communication
3. **VP Engineering** - For significant outages
4. **CEO** - For critical incidents (> 1 hour downtime)

## Communication Procedures

### Internal Communication

**During Incident:**
1. Update `#incidents-critical` channel
2. Post status updates every 15 minutes
3. Declare incident status: `INVESTIGATING` → `IDENTIFIED` → `MONITORING` → `RESOLVED`

**Status Update Template:**
```
[STATUS] Incident: High Error Rate
Time: 2026-08-26 10:30 UTC
Impact: API errors > 5%
Next Update: 10:45 UTC
Details: Investigating database connectivity...
```

### External Communication

**For customer-impacting incidents:**

1. **Initial notification** (within 15 minutes)
   - Post to status page
   - Send email to customers

2. **Updates** (every 30 minutes)
   - Update status page
   - Post on customer Slack

3. **Resolution** (when resolved)
   - Post incident summary
   - Send postmortem link

## Handoff Procedures

### Shift Handoff

**Daily Handoff (09:00 UTC):**

```bash
# Run handoff script
./scripts/on-call-handoff.sh --outgoing <username> --incoming <username>
```

**Handoff Checklist:**
- [ ] No open incidents
- [ ] No active silences
- [ ] Outstanding tasks documented
- [ ] Metrics dashboard reviewed
- [ ] Upcoming maintenance noted

### Weekly Handoff

**Every Monday 09:00 UTC:**

1. Review week's incidents
2. Discuss trends
3. Plan improvements
4. Update schedule

## On-Call Compensation

### Compensation Policy

- **Base**: On-call stipend of $X/week
- **Incident**: $Y/hour for incidents outside business hours
- **Postmortem**: 2 hours comp time for postmortem writeup

### Business Hours

- Monday-Friday: 09:00-18:00 UTC
- Incidents during business hours: No extra compensation
- Incidents outside business hours: Overtime rate

## Monitoring During On-Call

### Required Tools

1. **Slack** - Mobile app installed
2. **PagerDuty** - Mobile app installed
3. **Grafana** - Mobile access configured
4. **kubectl** - Remote access configured

### Check-in Schedule

- **Morning** (09:00 UTC): Check dashboards, review overnight
- **Mid-day** (15:00 UTC): Quick health check
- **Evening** (21:00 UTC): Verify all systems stable
- **Overnight**: Response to alerts only

### Health Check Commands

```bash
# Quick health check
curl http://localhost:8000/api/v1/health

# Check all pods
kubectl get pods -A

# Check error rates
curl http://localhost:8000/api/v1/metrics/error-rate

# Check SLO status
curl http://localhost:8000/api/v1/slo/all/status
```

## Training Requirements

### Before First On-Call Shift

1. **Shadow existing on-call** (1 week)
2. **Review all runbooks** (completed checklist)
3. **Run through fire drill** (simulate incident)
4. **Setup all tools** (Slack, PagerDuty, Grafana)

### Ongoing Training

- **Quarterly fire drills** - Simulate major incident
- **Monthly runbook review** - Update based on learnings
- **Annual training refresh** - Full review of procedures

## Incident Categories

### Common Incident Types

1. **Database Issues** - See [database-issues.md](runbooks/database-issues.md)
2. **High Error Rate** - See [high-error-rate.md](runbooks/high-error-rate.md)
3. **High Latency** - See [high-latency.md](runbooks/high-latency.md)
4. **SLO Violation** - See [slo-violation.md](runbooks/slo-violation.md)
5. **Resource Exhaustion** - See [resource-exhaustion.md](runbooks/resource-exhaustion.md)

### Special Incidents

- **Security Incident** - Escalate to security team immediately
- **Data Loss** - Page engineering lead, assess backup recovery
- **Provider Outage** - Follow provider status page, communicate ETA

## Metrics and KPIs

### On-Call Metrics

- **MTTA** (Mean Time To Acknowledge): Target < 15 minutes for P0
- **MTTR** (Mean Time To Resolve): Target < 1 hour for P0
- **Escalation Rate**: < 10% of incidents escalate
- **False Positive Rate**: < 5% of alerts

### Tracking

Metrics tracked in:
- Alertmanager silences
- PagerDuty incident reports
- Monthly on-call retrospective

## Emergency Contacts

| Role | Name | Slack | Phone | Email |
|------|------|-------|-------|-------|
| CTO | Jane Doe | @jane | +1-555-0101 | jane@company.com |
| VP Engineering | John Smith | @john | +1-555-0102 | john@company.com |
| Engineering Manager | Alice Johnson | @alice | +1-555-0103 | alice@company.com |
| Security Lead | Bob Wilson | @bob | +1-555-0104 | bob@company.com |

## Continuous Improvement

### Weekly Retrospective (Fridays 16:00 UTC)

- Review incidents from the week
- Identify trends
- Plan improvements

### Monthly Metrics Review (First Monday 10:00 UTC)

- Review on-call KPIs
- Assess alert fatigue
- Adjust thresholds

### Quarterly Process Review

- Update procedures based on feedback
- Review and update runbooks
- Assess on-call satisfaction

## Appendices

### A. Incident Template

```markdown
# Incident Report: [Title]

## Meta
- Date: YYYY-MM-DD
- Duration: X hours
- Severity: P0/P1/P2/P3
- Primary: @username
- Secondary: @username

## Summary
[Brief description of the incident]

## Timeline
- 10:00 UTC - Alert fired
- 10:15 UTC - Incident acknowledged
- 10:30 UTC - Root cause identified
- 11:00 UTC - Fix implemented
- 11:30 UTC - Resolved

## Root Cause
[What happened and why]

## Resolution
[What was done to fix it]

## Impact
[Services affected, customers impacted]

## Prevention
[What will prevent recurrence]
```

### B. Quick Commands

```bash
# Acknowledge all alerts
curl -X POST http://alertmanager:9093/api/v1/silences \
  -d '{"matchers":[{"name":"alertname","value":".*"}],"duration":"1h","comment":"Investigating"}'

# Check active silences
curl http://alertmanager:9093/api/v1/silences

# Get incident history
./scripts/get-incidents.sh --days 7
```
