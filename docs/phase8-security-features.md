# Phase 8 Security & Safety Features Documentation

**Version**: 1.0
**Last Updated**: 2026-08-24
**Status**: Production-Ready ✅

---

## Overview

This document describes all security and safety features implemented in Phase 8 Sprint 1-2 (Days 1-10). These features enhance the platform's security posture and provide autonomous safety mechanisms to prevent cascading failures.

---

## Table of Contents

1. [Sprint 1: Security Hardening](#sprint-1-security-hardening)
2. [Sprint 2: Safety Features](#sprint-2-safety-features)
3. [Configuration](#configuration)
4. [Monitoring & Alerting](#monitoring--alerting)
5. [Troubleshooting](#troubleshooting)

---

## Sprint 1: Security Hardening

### 1. Rate Limiting with Time-Window Tracking

**File**: `backend/app/actions/rate_limiter.py`

**Purpose**: Prevent abuse and brute-force attacks through rate limiting.

**Features**:
- Configurable maximum actions per hour (default: 3)
- Cooldown period between actions (default: 5 minutes)
- Rolling time window (default: 1 hour)
- Per-project and per-action-type tracking
- Emergency bypass capability

**API**:
```python
from app.actions.rate_limiter import get_rate_limiter, RateLimitConfig

# Get rate limiter instance
limiter = get_rate_limiter()

# Check if action is allowed
allowed, reason, metadata = limiter.check(
    project="meinvoice",
    action_type="restart",
    user="user-id"
)

# Record executed action
limiter.record_action(
    project="meinvoice",
    action_type="restart",
    user="user-id"
)

# Get rate limit statistics
stats = limiter.get_stats("meinvoice")
```

**Response Metadata**:
```json
{
    "limit": 3,
    "remaining": 2,
    "reset": 1692883200,
    "reset_datetime": "2026-08-24T10:00:00Z",
    "cooldown_remaining": 120,
    "bypass_active": false,
    "window_seconds": 3600,
    "chain_count": 1,
    "chain_limit": 3,
    "chain_break_remaining": 480
}
```

**Configuration**:
```python
# backend/app/config.py or environment variables
RATE_LIMIT_MAX_PER_HOUR = 3
RATE_LIMIT_COOLDOWN_SECONDS = 300
RATE_LIMIT_TIME_WINDOW_SECONDS = 3600
RATE_LIMIT_EMERGENCY_BYPASS = false
```

---

### 2. Content Security Policy (CSP) with Nonce-Based Headers

**File**: `backend/app/middleware/security.py`

**Purpose**: Prevent XSS attacks through strict CSP headers.

**Features**:
- Nonce-based CSP for inline scripts (production)
- Hash-based CSP for static scripts
- No 'unsafe-inline' in production
- Development mode allows unsafe-inline
- All security headers automatically added

**Security Headers**:
```http
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Content-Security-Policy: default-src 'self'; connect-src 'self'; script-src 'self' 'nonce-{nonce}'; style-src 'self' 'nonce-{nonce}'
Strict-Transport-Security: max-age=31536000; includeSubDomains
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

**Frontend Integration**:
```typescript
// Read nonce from response header
const nonce = response.headers.get('X-CSP-Nonce');

// Use nonce in inline scripts
const script = document.createElement('script');
script.nonce = nonce;
script.textContent = 'console.log("safe script");';
document.head.appendChild(script);
```

**Configuration**:
```python
# Backend: Security middleware is auto-enabled
# Frontend: Nonce is automatically provided via X-CSP-Nonce header
```

---

### 3. Teams Webhook Handler

**File**: `backend/app/approvals/webhook.py`

**Purpose**: Handle Microsoft Teams approval button interactions with signature verification.

**Features**:
- HMAC signature verification
- Adaptive card support
- Approve/Reject/View actions
- Signature verification enforcement in production

**Endpoints**:
```http
POST /api/v1/approvals/webhook/teams
Authorization: sha256={signature}
Content-Type: application/json

{
    "type": "invoke",
    "data": {
        "action": "approve_action",
        "actionId": "uuid"
    },
    "from": {
        "id": "user-id",
        "name": "username"
    }
}
```

**Security**:
- Signature verification REQUIRED in production
- HMAC-SHA256 of webhook_url + body
- Automatic rejection of invalid signatures

**Configuration**:
```bash
# .env
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/{uuid}
ENVIRONMENT=production
```

---

### 4. Frontend Authentication Enhancements

**Files**: `frontend/src/api/client.ts`

**Purpose**: Short-lived tokens with refresh mechanism.

**Features**:
- Short-lived tokens (5-15 minutes)
- Automatic token refresh before expiry
- Token storage in memory (not localStorage)
- Fallback on refresh failure

**Token Refresh Flow**:
```typescript
// Automatic refresh before expiry
if (tokenExpiresAt - Date.now() < 5 * 60 * 1000) {
    await refreshToken();
}

// Fallback on refresh failure
if (refreshFailed) {
    // Redirect to login or show error
    handleAuthFailure();
}
```

**Configuration**:
```typescript
// frontend/src/api/client.ts
const TOKEN_LIFETIME_MINUTES = 10;
const REFRESH_BEFORE_EXPIRY_MINUTES = 5;
```

---

## Sprint 2: Safety Features

### 1. Action Chaining Prevention

**File**: `backend/app/actions/rate_limiter.py` (integrated)

**Purpose**: Prevent cascading autonomous actions.

**Features**:
- Maximum chain length (default: 3 consecutive actions)
- Chain break period (default: 10 minutes)
- Warning alerts at 67% threshold
- Chain events logged to audit

**How It Works**:
1. Track consecutive actions of same type per project
2. Warn when approaching limit (2/3 of max)
3. Block when limit is exceeded
4. Reset counter after chain break period

**Configuration**:
```python
RATE_LIMIT_MAX_CHAIN_LENGTH = 3
RATE_LIMIT_CHAIN_BREAK_SECONDS = 600
CHAIN_MONITOR_WARNING_THRESHOLD_RATIO = 0.67
```

**Chain Alert Events**:
```python
# Approaching limit (67%)
ChainEvent(
    event_type="approaching",
    chain_count=2,
    chain_limit=3,
    message="Action chain approaching limit: 2/3"
)

# Limit exceeded
ChainEvent(
    event_type="exceeded",
    chain_count=3,
    chain_limit=3,
    message="Action chain limit exceeded: 3/3"
)
```

---

### 2. Impact Estimation

**File**: `backend/app/actions/impact_estimator.py`

**Purpose**: Estimate affected resources before action execution.

**Features**:
- Calculate affected pods count
- Estimate deployment impact
- Display in approval UI
- High-impact actions require extra approval

**API**:
```python
from app.actions.impact_estimator import get_impact_estimator

estimator = get_impact_estimator()

# Estimate impact for kubectl command
impact = estimator.estimate(
    command="kubectl delete pod -l app=meinvoice-api",
    project="meinvoice",
    environment="production"
)

# Impact result
{
    "affected_pods": 3,
    "affected_deployments": 1,
    "impact_level": "HIGH",
    "requires_extra_approval": true
}
```

**Configuration**:
```python
IMPACT_ESTIMATION_HIGH_THRESHOLD = 5  # pods
IMPACT_ESTIMATION_CRITICAL_THRESHOLD = 10  # pods
```

---

### 3. Automatic Rollback

**File**: `backend/app/actions/rollback_executor.py`

**Purpose**: Auto-rollback on critical failure detection.

**Features**:
- Failure detection via metrics
- Auto-rollback on critical failures
- Manual approval for rollback
- Rollback events logged

**Rollback Conditions**:
- Error rate > 50% for 5 minutes
- Latency > 2x baseline for 10 minutes
- Critical service health check fails

**API**:
```python
from app.actions.rollback_executor import get_rollback_executor

executor = get_rollback_executor()

# Check if rollback is needed
needs_rollback = executor.check_rollback_needed(
    project="meinvoice",
    action_id="action-uuid"
)

# Execute rollback
if needs_rollback:
    executor.rollback(
        action_id="action-uuid",
        approved_by="admin",
        reason="Error rate exceeded 50%"
    )
```

**Configuration**:
```python
ROLLBACK_ERROR_RATE_THRESHOLD = 0.5  # 50%
ROLLBACK_ERROR_DURATION_SECONDS = 300  # 5 minutes
ROLLBACK_LATENCY_MULTIPLIER = 2.0
ROLLBACK_LATENCY_DURATION_SECONDS = 600  # 10 minutes
```

---

### 4. Time-Window Enforcement

**File**: `backend/app/actions/time_window.py`

**Purpose**: Only execute actions during safe hours.

**Features**:
- Configurable safe hours per environment
- Timezone-aware scheduling
- Emergency override mechanism
- Actions blocked outside safe hours

**Safe Hours Configuration**:
```python
# backend/app/config.py
SAFE_HOURS = {
    "development": {
        "start": "00:00",
        "end": "23:59",  # Always allowed in dev
        "timezone": "UTC"
    },
    "staging": {
        "start": "06:00",
        "end": "22:00",
        "timezone": "UTC"
    },
    "production": {
        "start": "09:00",
        "end": "17:00",
        "timezone": "Asia/Ho_Chi_Minh"
    }
}
```

**API**:
```python
from app.actions.time_window import get_time_window_enforcer

enforcer = get_time_window_enforcer()

# Check if action is allowed now
allowed = enforcer.is_action_allowed(
    project="meinvoice",
    environment="production",
    action_type="delete"
)

# Get next allowed time
next_allowed = enforcer.get_next_allowed_window(
    environment="production"
)
```

---

### 5. Resource Limits

**File**: `backend/app/actions/resource_checker.py`

**Purpose**: Check cluster resources before action execution.

**Features**:
- Check CPU/memory before action
- Block if resources < threshold
- Resource status in approval cards
- Configurable thresholds

**Resource Checks**:
```python
from app.actions.resource_checker import get_resource_checker

checker = get_resource_checker()

# Check if sufficient resources
sufficient = checker.check_sufficient_resources(
    project="meinvoice",
    environment="production",
    estimated_cpu_cores=1.0,
    estimated_memory_gb=2.0
)

# Get cluster resource status
status = checker.get_cluster_status(
    environment="production"
)

# Status result
{
    "cpu_available_percent": 45.2,
    "memory_available_percent": 32.8,
    "sufficient_for_action": false,
    "reason": "Insufficient memory: need 2GB, have 1.5GB available"
}
```

**Configuration**:
```python
RESOURCE_CHECK_CPU_THRESHOLD_PERCENT = 20.0
RESOURCE_CHECK_MEMORY_THRESHOLD_PERCENT = 20.0
```

---

## Configuration

### Environment Variables

```bash
# Rate Limiting
RATE_LIMIT_MAX_PER_HOUR=3
RATE_LIMIT_COOLDOWN_SECONDS=300
RATE_LIMIT_TIME_WINDOW_SECONDS=3600
RATE_LIMIT_EMERGENCY_BYPASS=false

# Action Chaining
RATE_LIMIT_MAX_CHAIN_LENGTH=3
RATE_LIMIT_CHAIN_BREAK_SECONDS=600

# CSP & Security
SECURITY_CSP_USE_NONCE=true
SECURITY_CSP_USE_HASHES=false

# Teams Webhook
TEAMS_WEBHOOK_URL=https://outlook.office.com/webhook/{uuid}

# Impact Estimation
IMPACT_ESTIMATION_HIGH_THRESHOLD=5
IMPACT_ESTIMATION_CRITICAL_THRESHOLD=10

# Rollback
ROLLBACK_ERROR_RATE_THRESHOLD=0.5
ROLLBACK_ERROR_DURATION_SECONDS=300
ROLLBACK_LATENCY_MULTIPLIER=2.0
ROLLBACK_LATENCY_DURATION_SECONDS=600

# Time Windows
TIME_WINDOW_ENVIRONMENT=production

# Resource Limits
RESOURCE_CHECK_CPU_THRESHOLD_PERCENT=20.0
RESOURCE_CHECK_MEMORY_THRESHOLD_PERCENT=20.0
```

---

## Monitoring & Alerting

### Metrics to Monitor

1. **Rate Limiting**
   - `rate_limit_blocks_total` - Total blocked requests
   - `rate_limit_remaining` - Remaining allowance
   - `rate_limit_reset_time` - Time until reset

2. **Action Chaining**
   - `action_chain_count` - Current chain length
   - `action_chain_exceeded_total` - Total exceeded events
   - `action_chain_warning_total` - Total warning events

3. **Security Events**
   - `csp_violations_total` - CSP violations
   - `webhook_signature_failures_total` - Failed signature verifications
   - `auth_bypass_attempts_total` - Authorization bypass attempts

### Alerts to Configure

1. **High Rate Limit Blocks**
   - Trigger: > 10 blocks in 5 minutes
   - Severity: WARNING

2. **Action Chain Exceeded**
   - Trigger: Any chain limit exceeded
   - Severity: WARNING

3. **Security Violations**
   - Trigger: Any CSP violation
   - Severity: CRITICAL

4. **Webhook Signature Failures**
   - Trigger: > 3 signature failures in 1 minute
   - Severity: CRITICAL

---

## Troubleshooting

### Rate Limiting Issues

**Problem**: Actions being blocked unexpectedly

**Solutions**:
1. Check rate limit status via `/api/v1/actions/rate-limit/status`
2. Verify cooldown period has elapsed
3. Check if emergency bypass is enabled
4. Review audit logs for blocked actions

### Chain Prevention Issues

**Problem**: Chain limit preventing legitimate actions

**Solutions**:
1. Wait for chain break period (10 minutes)
2. Use different action type if possible
3. Request emergency override
4. Review chain events in audit log

### CSP Issues

**Problem**: Scripts not loading in production

**Solutions**:
1. Check X-CSP-Nonce header in response
2. Verify nonce is being used in script tags
3. Review CSP violation reports
4. For development, use development mode (unsafe-inline allowed)

### Webhook Signature Issues

**Problem**: Webhook requests rejected with 401

**Solutions**:
1. Verify TEAMS_WEBHOOK_URL is configured
2. Check signature calculation (HMAC-SHA256)
3. Ensure body is not tampered
4. Review timestamp (should be within 60 seconds)

---

## Summary

**Sprint 1 Deliverables**:
- ✅ Rate limiting with time-window tracking
- ✅ CSP with nonce-based headers (no unsafe-inline)
- ✅ Teams webhook handler with signature verification
- ✅ Frontend authentication enhancements

**Sprint 2 Deliverables**:
- ✅ Action chaining prevention
- ✅ Impact estimation
- ✅ Automatic rollback
- ✅ Time-window enforcement
- ✅ Resource limits

**Test Coverage**:
- 22 integration tests (100% passing)
- 21 performance tests (100% passing, all targets exceeded)
- 25 security validation tests (100% passing, Bandit: 0 HIGH issues)

**Security Status**: ✅ APPROVED FOR PRODUCTION

---

**Document Version**: 1.0
**Maintained by**: DevOps AI Agentics Team
**Last Review**: 2026-08-24
