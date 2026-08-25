# Phase 8 Operations Runbook

**Version**: 1.0
**Last Updated**: 2026-08-24
**Audience**: Platform Operators, SREs

---

## Overview

This runbook provides operational procedures for managing the DevOps AI Agentics platform with Phase 8 security and safety features enabled.

---

## Table of Contents

1. [Daily Operations](#daily-operations)
2. [Incident Response](#incident-response)
3. [Security Events](#security-events)
4. [Maintenance Procedures](#maintenance-procedures)
5. [Emergency Procedures](#emergency-procedures)

---

## Daily Operations

### Morning Checklist

**Every day at 09:00 AM**:

```bash
# 1. Check platform health
curl https://platform.example.com/api/v1/health

# 2. Review security events (last 24 hours)
curl https://platform.example.com/api/v1/audit/events \
  -H "Authorization: Bearer $TOKEN" \
  -d "event_type=security_check" \
  -d "last_hours=24"

# 3. Check rate limit status
curl https://platform.example.com/api/v1/actions/rate-limit/status

# 4. Review blocked actions
curl https://platform.example.com/api/v1/actions/blocked \
  -H "Authorization: Bearer $TOKEN"
```

### Weekly Review

**Every Friday**:

1. Review all audit logs for the week
2. Check for pattern of rate limit blocks
3. Review action chain exceeded events
4. Verify CSP violations (should be zero)
5. Review webhook signature failures

---

## Incident Response

### Rate Limit Breach

**Symptom**: Users report actions being blocked

**Severity**: MEDIUM

**Response**:

```bash
# 1. Check rate limit status
curl https://platform.example.com/api/v1/actions/rate-limit/status

# 2. Review audit logs for blocks
curl https://platform.example.com/api/v1/audit/events \
  -H "Authorization: Bearer $TOKEN" \
  -d "event_type=rate_limit_block"

# 3. If legitimate activity, increase limit temporarily
curl https://platform.example.com/api/v1/actions/rate-limit/config \
  -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -d "max_per_hour=10"

# 4. Monitor for 1 hour, then revert
curl https://platform.example.com/api/v1/actions/rate-limit/config \
  -X PATCH \
  -H "Authorization: Bearer $TOKEN" \
  -d "max_per_hour=3"
```

### Chain Limit Exceeded

**Symptom**: Autonomous actions blocked due to chain limit

**Severity**: MEDIUM

**Response**:

```bash
# 1. Review chain events
curl https://platform.example.com/api/v1/audit/events \
  -H "Authorization: Bearer $TOKEN" \
  -d "event_type=chain_exceeded"

# 2. Investigate root cause (may indicate automation loop)

# 3. If legitimate, wait for chain break period (10 minutes)
# Or use emergency override for critical actions

curl https://platform.example.com/api/v1/actions/execute \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"command": "...", "emergency_override": true}'
```

### Security Violation Detected

**Symptom**: CSP violation, auth bypass attempt, or webhook signature failure

**Severity**: CRITICAL

**Response**:

```bash
# 1. Immediately investigate the violation
curl https://platform.example.com/api/v1/audit/events \
  -H "Authorization: Bearer $TOKEN" \
  -d "event_type=security_violation"

# 2. Review source IP and user agent
curl https://platform.example.com/api/v1/audit/events \
  -H "Authorization: Bearer $TOKEN" \
  -d "last_hours=1"

# 3. If attack in progress, enable emergency mode
curl https://platform.example.com/api/v1/admin/emergency \
  -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 4. Escalate to security team
# 5. Document incident in post-mortem
```

---

## Security Events

### CSP Violation

**Meaning**: Browser blocked resource due to Content Security Policy

**Response**:

1. Check CSP policy in security middleware
2. Verify nonce is being used correctly
3. Update CSP policy if needed
4. Review violation report in browser console

### Webhook Signature Failure

**Meaning**: Webhook request from Slack/Teams failed signature verification

**Response**:

1. Verify webhook URL configuration
2. Check signing secret/shared secret
3. Ensure request body is not modified
4. Review timestamp (must be within 60 seconds)

### Rate Limit Exhaustion

**Meaning**: Project has exceeded maximum actions per hour

**Response**:

1. Review project activity
2. Check for automation loops
3. If legitimate, consider increasing limit
4. Monitor for repeated patterns

---

## Maintenance Procedures

### Updating Rate Limit Configuration

```bash
# Backup current configuration
curl https://platform.example.com/api/v1/actions/rate-limit/config \
  -H "Authorization: Bearer $TOKEN" > rate-limit-backup.json

# Update configuration
curl https://platform.example.com/api/v1/actions/rate-limit/config \
  -X PUT \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "max_actions_per_hour": 5,
    "cooldown_seconds": 300,
    "time_window_seconds": 3600,
    "max_chain_length": 3,
    "chain_break_seconds": 600
  }'

# Verify new configuration
curl https://platform.example.com/api/v1/actions/rate-limit/status
```

### Updating Safe Hours

```python
# Update in backend/app/config.py or via environment variable
SAFE_HOURS = {
    "production": {
        "start": "08:00",
        "end": "20:00",
        "timezone": "Asia/Ho_Chi_Minh"
    }
}

# Restart backend service
kubectl rollout restart deployment/backend -n production
```

### Rotating Webhook Secrets

```bash
# 1. Generate new webhook URL in Teams/Slack
# 2. Update configuration

# For Slack
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/NEW/URL/HERE"

# For Teams
export TEAMS_WEBHOOK_URL="https://outlook.office.com/webhook/NEW/UUID"

# 3. Restart backend service
kubectl rollout restart deployment/backend -n production

# 4. Test new webhook
curl https://platform.example.com/api/v1/approvals/webhook/test \
  -X POST \
  -H "Authorization: Bearer $TOKEN"
```

---

## Emergency Procedures

### Emergency Bypass Activation

**When to use**: Critical incident requiring immediate action

**Procedure**:

```bash
# Enable emergency bypass (allows all actions)
curl https://platform.example.com/api/v1/admin/emergency/bypass \
  -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": true, "reason": "Incident #12345"}'

# Execute required action
curl https://platform.example.com/api/v1/actions/execute \
  -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"command": "kubectl ..."}'

# Disable emergency bypass after incident resolved
curl https://platform.example.com/api/v1/admin/emergency/bypass \
  -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": false, "reason": "Incident resolved"}'
```

### Platform Lockdown

**When to use**: Security breach detected

**Procedure**:

```bash
# Enable lockdown mode (read-only)
curl https://platform.example.com/api/v1/admin/lockdown \
  -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": true, "reason": "Security incident"}'

# All actions will be blocked except read operations

# To disable
curl https://platform.example.com/api/v1/admin/lockdown \
  -X POST \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"enabled": false, "reason": "Investigation complete"}'
```

### Rollback to Previous Version

**When to use**: New features causing issues

**Procedure**:

```bash
# Check current version
kubectl describe deployment/backend -n production | grep Image

# Rollback to previous revision
kubectl rollout undo deployment/backend -n production

# Verify rollback
kubectl rollout status deployment/backend -n production
```

---

## Monitoring

### Key Metrics to Monitor

1. **Security Metrics**
   - `security_events_total` - Total security events
   - `csp_violations_total` - CSP violations
   - `webhook_signature_failures_total` - Failed signature verifications

2. **Rate Limiting Metrics**
   - `rate_limit_blocks_total` - Total blocked requests
   - `rate_limit_reset_count` - Rate limit reset events

3. **Chain Prevention Metrics**
   - `action_chain_exceeded_total` - Chain limit exceeded events
   - `action_chain_warning_total` - Chain warning events

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| CSP violations | > 0/hour | > 10/hour |
| Webhook failures | > 5/hour | > 20/hour |
| Rate limit blocks | > 50/hour | > 100/hour |
| Chain exceeded | > 5/hour | > 10/hour |

---

## Escalation Matrix

| Severity | Response Time | Escalation |
|----------|---------------|------------|
| P1 - Critical | 15 minutes | Engineering Manager + CTO |
| P2 - High | 1 hour | Engineering Manager |
| P3 - Medium | 4 hours | Team Lead |
| P4 - Low | 2 days | None (backlog) |

---

## Contacts

| Role | Name | Email | On-Call |
|------|------|-------|---------|
| Platform Lead | | | @platform-oncall |
| Security Lead | | | @security-oncall |
| SRE Lead | | | @sre-oncall |

---

## Summary

**Procedures Covered**:
- Daily operations checklist
- Incident response procedures
- Security event handling
- Maintenance procedures
- Emergency procedures

**Key Takeaways**:
1. Always review audit logs for security events
2. Emergency bypass should be used sparingly and documented
3. Rate limit configuration changes require monitoring
4. All security violations should be investigated

**Training Requirements**:
- All operators should complete Phase 8 security training
- Monthly incident response drills recommended
- Quarterly security review required

---

**Runbook Version**: 1.0
**Maintained by**: DevOps AI Agentics Team
**Last Review**: 2026-08-24
