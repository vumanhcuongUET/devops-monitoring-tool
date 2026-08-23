# Security Documentation

## Threat Model

### Overview

The AI Assistant security model is based on the following assumptions and threat scenarios:

### Trust Boundaries

**Trusted Components:**
- Internal codebase (`ai_assistant/` module)
- Backend integration adapters (`services/` module)
- Local configuration files (`config/`, `projects/`)

**Untrusted Inputs:**
- User-provided command-line arguments
- YAML configuration files (may be edited by users)
- Environment variables (may be set by different users)
- Template variables from query definitions

### Threat Scenarios

#### 1. Command Injection (MITIGATION: ✅ IMPLEMENTED)

**Threat**: Attacker injects malicious commands through:
- Malicious project/section names
- Malicious time range parameters
- Malicious PromQL queries
- Malicious template content

**Mitigations**:
- `InputValidator.validate_project_name()` - Only allows alphanumeric, hyphens, underscores
- `InputValidator.validate_time_range()` - Strict format validation
- `InputValidator.validate_promql()` - Checks for dangerous patterns (XSS, script tags)
- `InputValidator.validate_template_content()` - Detects injection patterns (PHP tags, JSP tags, template injection)

#### 2. URL/SSRF Attacks (MITIGATION: ✅ IMPLEMENTED)

**Threat**: Attacker causes requests to malicious URLs through:
- Malicious source URLs in configuration
- Redirect chains to internal services

**Mitigations**:
- `InputValidator.validate_url()` - Only allows http:// and https:// protocols
- Protocol validation to block javascript:, data:, vbscript: URIs
- Credential sanitization in logs (`InputValidator.sanitize_url()`)

#### 3. Resource Exhaustion (MITIGATION: ✅ IMPLEMENTED)

**Threat**: Attacker causes DoS through:
- excessively large query bodies
- excessively long PromQL queries
- excessive query rate

**Mitigations**:
- `InputValidator.MAX_LENGTHS` - Enforces size limits on inputs
- `TokenBucketRateLimiter` - Rate limits per-identifier
- Query timeout enforcement (configurable `timeout_seconds`)

#### 4. Audit Log Tampering (MITIGATION: ✅ IMPLEMENTED)

**Threat**: Attacker modifies or deletes audit logs to hide malicious activity

**Mitigations**:
- Chain hashing (HMAC-SHA256) - Each entry includes hash of previous entries
- Secret key stored in protected file (`.secret` with 0600 permissions)
- `verify_integrity()` method detects tampering
- Immutable append-only file writes

#### 5. Template Injection (MITIGATION: ✅ IMPLEMENTED)

**Threat**: Attacker injects malicious template code through:
- Malicious template variables
- Complex nested template expressions

**Mitigations**:
- `InputValidator.validate_template_content()` - Detects dangerous patterns
- Nesting depth limit (max 20 levels) to prevent DoS
- Length limits on templates

### Security Assumptions

1. **File System**: The code assumes the file system is trusted and not subject to TOCTOU races between validation and usage. For production, consider atomic file operations.

2. **Secret Storage**: The audit log secret (`.secret` file) assumes file permissions are respected. Ensure proper file system permissions on the `data/audit/` directory.

3. **Environment Variables**: The code assumes environment variables are set by trusted sources. Consider using a secrets manager for production.

4. **Backend Integration**: When backend integration is enabled, the code assumes the backend service (`backend/app/main.py`) is trusted and properly secured.

### Known Limitations

1. **No Authentication**: The AI Assistant does not implement user authentication. It relies on:
   - File system permissions
   - RBAC at the backend level
   - Environment-based access control

2. **No Encryption**: Audit logs are stored in plain text. For sensitive environments, consider:
   - Encrypting audit logs at rest
   - Using signed audit logs
   - Sending logs to a centralized SIEM

3. **No Input Sanitization for Query Bodies**: The query body size is validated, but the content is not deeply inspected. Malformed queries will fail at the Elasticsearch/Prometheus level.

4. **Race Conditions in File Operations**: File operations (read, write) are not atomic. For high-concurrency scenarios, consider file locking.

### Defense in Depth

The security architecture follows defense-in-depth principles:

**Layer 1 - Input Validation**:
- Type checking
- Length limits
- Format validation
- Pattern matching

**Layer 2 - Rate Limiting**:
- Token bucket algorithm
- Per-identifier limits
- Configurable burst capacity

**Layer 3 - Audit Logging**:
- Tamper-evident storage
- Chain hashing
- Integrity verification

**Layer 4 - Network Security**:
- Protocol validation
- URL sanitization
- Credential redaction

**Layer 5 - Operational Security**:
- Structured logging
- Error handling
- Graceful degradation

### Testing

Security tests are located in:
- `tests/test_security.py` - Input validation, rate limiting, URL validation
- `tests/test_audit.py` - Audit logging, tamper detection

Run security tests:
```bash
python -m pytest tests/test_security.py tests/test_audit.py -v
```

### Incident Response

If a security incident is suspected:

1. **Verify Audit Log Integrity**:
   ```python
   from core.audit import get_audit_logger
   logger = get_audit_logger()
   result = logger.verify_integrity()
   if not result["valid"]:
       # Logs have been tampered with
       alert_security_team()
   ```

2. **Review Audit Logs**:
   ```python
   # Query for suspicious activity
   results = logger.query(
       actor="suspicious_user",
       start_time=incident_start_time,
       limit=1000
   )
   ```

3. **Check Rate Limit Violations**:
   ```python
   from core.logging_config import get_metrics
   metrics = get_metrics()
   rate_limit_exceeded = metrics.get("rate_limit_exceeded_total")
   ```

### Compliance

The audit logging feature supports compliance requirements for:

- **SOC 2**: Access logging, tamper detection
- **GDPR**: Audit trail of data processing activities
- **PCI DSS**: Access monitoring and logging
- **HIPAA**: Audit controls for PHI access

---

**Document Version**: 1.0  
**Last Updated**: 2026-08-24  
**Maintained by**: DevOps AI Agentics Team
