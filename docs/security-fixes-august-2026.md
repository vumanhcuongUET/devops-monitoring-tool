# Security Fixes - August 2026

This document describes security vulnerabilities identified and fixed in the `fix/critical-security-issues` branch.

## Summary

Three security vulnerabilities were identified and fixed:

1. **Command executor whitelist not enforced** (HIGH severity)
2. **Teams webhook authentication bypass** (HIGH severity)
3. **Unauthenticated metrics endpoint** (MEDIUM severity)

---

## Vulnerability 1: Command Whitelist Not Enforced

**File:** `backend/app/actions/executor.py:19-34`

**Severity:** HIGH

**Description:**
The `CommandExecutor` class defined a `ALLOWED_COMMANDS` whitelist but never used it for validation. Only forbidden pattern checks were performed, meaning ANY command binary could be executed, not just kubectl/helm/argocd.

**Exploit Scenario:**
An attacker could supply arbitrary command binaries (e.g., `rm`, `cat`, `bash`) and they would be executed despite the whitelist being present in the code.

**Fix Applied:**
- Added validation in `_execute_safe()` to check `cmd_args[0]` against `ALLOWED_COMMANDS.keys()`
- Added flag validation to ensure only allowed flags and global flags are used per command
- Returns error with list of allowed commands if validation fails

**Code Changes:**
```python
# Before: No whitelist validation
async def _execute_safe(self, cmd_args, dry_run=False, timeout_seconds=300):
    # ... no validation of command name ...

# After: Full whitelist validation
async def _execute_safe(self, cmd_args, dry_run=False, timeout_seconds=300):
    # Validate command is in whitelist
    command_name = cmd_args[0]
    if command_name not in self.ALLOWED_COMMANDS:
        allowed = ", ".join(self.ALLOWED_COMMANDS.keys())
        return ExecutionResult(success=False, error_message=f"Command '{command_name}' is not allowed. Allowed: {allowed}")

    # Validate flags and arguments
    allowed_config = self.ALLOWED_COMMANDS[command_name]
    # ... flag validation ...
```

---

## Vulnerability 2: Teams Webhook Authentication Bypass

**File:** `backend/app/approvals/webhook.py:277-282`

**Severity:** HIGH

**Description:**
The Teams webhook endpoint used the wrong configuration variable (`SLACK_APPROVAL_WEBHOOK_URL`) for signature verification and fell back to insecure mode when not configured, allowing fake approval/rejection requests.

**Exploit Scenario:**
When `SLACK_APPROVAL_WEBHOOK_URL` was empty or the `Authorization` header was missing, the Teams webhook accepted requests without any signature verification. An attacker could send fake approval/rejection requests to bypass the approval workflow.

**Fix Applied:**
- Added dedicated `TEAMS_WEBHOOK_URL` and `TEAMS_SIGNING_SECRET` config variables
- Modified webhook to fail hard (HTTP 500) when signature verification is not configured in production
- In non-production environments, logs a warning but still allows requests
- Updated `.env.example` with new config variables

**Code Changes:**
```python
# Before: Used wrong config and allowed insecure fallback
if settings.SLACK_APPROVAL_WEBHOOK_URL and authorization:
    # verify...
else:
    logger.warning("Teams webhook signature verification skipped (INSECURE!)")

# After: Proper config with production fail-hard
if settings.ENVIRONMENT == "production":
    if not settings.TEAMS_WEBHOOK_URL:
        raise HTTPException(status_code=500, detail="Signature verification not configured")
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")
    if not verify_teams_hmac_signature(...):
        raise HTTPException(status_code=401, detail="Invalid signature")
```

**Config Changes:**
```python
# Added to config.py
TEAMS_WEBHOOK_URL: str = ""
TEAMS_SIGNING_SECRET: str = ""

# Added to .env.example
TEAMS_WEBHOOK_URL=
TEAMS_SIGNING_SECRET=
```

---

## Vulnerability 3: Unauthenticated Metrics Endpoint

**File:** `backend/app/api/v1/metrics.py:56-59`

**Severity:** MEDIUM

**Description:**
The `/metrics` Prometheus endpoint was publicly accessible without authentication, exposing internal system metrics and operational patterns.

**Exploit Scenario:**
An unauthenticated attacker could scrape `/metrics` to view HTTP request rates, LLM usage patterns, action execution statistics, and other operational data that could aid in reconnaissance for further attacks.

**Fix Applied:**
- Added `verify_metrics_auth()` dependency that validates API key or bearer token
- Updated `/metrics` endpoint to require authentication
- Updated README with authentication configuration for Prometheus

**Code Changes:**
```python
# Added authentication dependency
async def verify_metrics_auth(request: Request) -> None:
    """Verify authentication for metrics endpoint."""
    if not settings.AUTH_ENABLED:
        return

    api_key = request.headers.get("X-API-Key")
    if api_key and _is_valid_api_key(api_key):
        return

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _is_valid_token(token):
            return

    raise HTTPException(status_code=401, detail="Authentication required")

@router.get("/metrics", dependencies=[Depends(verify_metrics_auth)])
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type="text/plain")
```

**Prometheus Configuration:**
Users must now configure authentication in their Prometheus scrape config:
```yaml
bearer_token: your-api-token
# or
headers:
  X-API-Key: your-api-key
```

---

## Verification Checklist

After applying these fixes, verify:

- [ ] Command executor rejects unknown commands (e.g., `rm`, `cat`, `bash`)
- [ ] Command executor validates flags against whitelist
- [ ] Teams webhook requires signature verification in production
- [ ] Teams webhook fails with proper error when not configured
- [ ] Metrics endpoint returns 401 without authentication
- [ ] Metrics endpoint accepts valid API key or bearer token
- [ ] README documents new authentication requirements

---

## Migration Notes

### For Metrics Endpoint

If you have Prometheus scraping `/metrics`, update your configuration:

```yaml
scrape_configs:
  - job_name: 'devops-monitoring'
    static_configs:
      - targets: ['backend:8000']
    # Add one of:
    bearer_token: 'your-api-token-here'
    # OR
    headers:
      X-API-Key: 'your-api-key-here'
```

### For Teams Webhook

If using Teams approval webhooks, add new config variables:

```bash
TEAMS_WEBHOOK_URL=https://your-teams.webhook.url
TEAMS_SIGNING_SECRET=your-teams-signing-secret
```

---

## Files Modified

- `backend/app/actions/executor.py` - Added command whitelist validation
- `backend/app/approvals/webhook.py` - Fixed Teams webhook authentication
- `backend/app/api/v1/metrics.py` - Added authentication requirement
- `backend/app/config.py` - Added TEAMS_WEBHOOK_URL and TEAMS_SIGNING_SECRET
- `.env.example` - Added new config variables
- `README.md` - Updated security documentation and config reference

---

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
