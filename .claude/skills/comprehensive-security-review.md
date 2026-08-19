# Comprehensive Security & DevOps Review Skill

Combines all security and DevOps best practices into one comprehensive review skill.

## Overview

This skill performs a comprehensive security and DevOps review by checking multiple aspects:

1. **General Security** - Injection vulnerabilities, authentication, secrets
2. **Python Security** - Python-specific vulnerabilities
3. **FastAPI Security** - FastAPI-specific security
4. **React/TypeScript Security** - Frontend security
5. **API Security** - REST API security
6. **Database Security** - Database operations security
7. **Container Security** - Docker and container security
8. **Kubernetes Security** - K8s manifests security
9. **Infrastructure Security** - Cloud infrastructure security
10. **DevOps Best Practices** - Reliability and operational excellence

## Usage

When reviewing code changes, this skill automatically:

- Checks for security vulnerabilities
- Verifies DevOps best practices
- Suggests improvements and fixes
- Prioritizes findings by severity

## Review Process

### Step 1: Identify Technology Stack

Determine which review skills apply based on:

- File extensions (.py, .ts, .tsx, .yaml, .dockerfile, etc.)
- Framework usage (FastAPI, React, etc.)
- Infrastructure type (Kubernetes, Terraform, etc.)

### Step 2: Apply Relevant Skills

Run appropriate security checks based on technology stack:

**For Python/FastAPI:**
- `python-security.md`
- `fastapi-security.md`
- `database-security.md`
- `api-security.md`

**For Frontend (React/TypeScript):**
- `react-security.md`
- `api-security.md`

**For Infrastructure:**
- `k8s-review.md`
- `container-security.md`
- `infrastructure-security.md`

**For All:**
- `security-review.md`
- `devops-review.md`

### Step 3: Consolidate Findings

Combine findings from all relevant skills into a unified report.

### Step 4: Prioritize by Severity

Order findings:
1. **Critical** - Immediate security vulnerabilities
2. **High** - Important security issues
3. **Medium** - Security best practices
4. **Low** - Minor improvements

## Review Checklist

### Universal Security Checks (Apply to All Code)

- [ ] No hardcoded secrets or credentials
- [ ] Input validation and sanitization
- [ ] Proper error handling without exposing sensitive information
- [ ] Authentication and authorization where required
- [ ] Security headers configured
- [ ] Logging doesn't expose sensitive data
- [ ] Dependencies are up to date and secure

### Code-Specific Checks

**Python/FastAPI:**
- [ ] Parameterized queries (no SQL injection)
- [ ] No pickle deserialization of untrusted data
- [ ] PyYAML safe_load instead of load
- [ ] SSL/TLS certificate verification
- [ ] Cryptographically secure random generation
- [ ] Authentication required for protected endpoints
- [ ] Rate limiting configured
- [ ] CORS configured with specific origins

**React/TypeScript:**
- [ ] No dangerouslySetInnerHTML without sanitization
- [ ] No secrets in client-side code
- [ ] Token expiration checked
- [ ] Content Security Policy configured
- [ ] URL parameters validated
- [ ] No unsafe type assertions

**API:**
- [ ] Proper HTTP methods
- [ ] API versioning
- [ ] Pagination with limits
- [ ] Mass assignment protection
- [ ] API keys in headers, not URL

**Database:**
- [ ] Encrypted connections
- [ ] Passwords hashed
- [ ] Least privilege database users
- [ ] Transaction management
- [ ] Connection cleanup

**Containers:**
- [ ] Minimal base images
- [ ] Non-root user
- [ ] No secrets in image
- [ ] Health checks
- [ ] Resource limits

**Kubernetes:**
- [ ] Resource requests and limits
- [ ] No privileged containers
- [ ] No hostNetwork/hostPID
- [ ] Security context configured
- [ ] Network policies
- [ ] RBAC least privilege

**Infrastructure:**
- [ ] No hardcoded credentials
- [ ] S3 blocks public access
- [ ] Security groups restrict access
- [ ] Encryption enabled
- [ ] CloudTrail enabled
- [ ] Multi-AZ for high availability

### DevOps Best Practices

- [ ] Timeouts on all external calls
- [ ] Retry logic for transient failures
- [ ] Circuit breaker for downstream services
- [ ] Structured logging with context
- [ ] Metrics for key operations
- [ ] Health check endpoints
- [ ] Graceful degradation with fallbacks
- [ ] Rate limiting for expensive operations
- [ ] Graceful shutdown handling

## Output Format

```markdown
# Comprehensive Security & DevOps Review: [project_name]

## Executive Summary
- **Files Reviewed**: [count]
- **Critical Issues**: [count]
- **High Issues**: [count]
- **Medium Issues**: [count]
- **Low Issues**: [count]
- **Positive Patterns**: [count]

## Critical Findings
### [file_name:line]
**Issue**: [Brief description]
**Risk**: [Security impact]
**Recommendation**: [Fix]

## High Findings
### [file_name:line]
**Issue**: [Brief description]
**Risk**: [Security impact]
**Recommendation**: [Fix]

## Medium Findings
[Same format]

## Low Findings
[Same format]

## Positive Patterns
+ [Good practice found in file_name:line]

## Technology Stack Analysis
- **Backend**: [Technologies]
- **Frontend**: [Technologies]
- **Infrastructure**: [Technologies]
- **Database**: [Technologies]
- **Containers**: [Technologies]

## Recommendations Summary
1. [Priority 1 - Critical security fixes]
2. [Priority 2 - High priority improvements]
3. [Priority 3 - Medium priority enhancements]
4. [Priority 4 - Low priority optimizations]
```

## Quick Reference

### Critical Issues That Require Immediate Action

1. **SQL Injection** - Use parameterized queries
2. **Command Injection** - Avoid shell=True, use list arguments
3. **Hardcoded Secrets** - Use environment variables or secret managers
4. **Missing Authentication** - Add auth to protected endpoints
5. **Authorization Bypass** - Check resource ownership
6. **Public S3 Buckets** - Block public access
7. **Root Containers** - Run as non-root
8. **Security Groups 0.0.0.0/0** - Restrict to specific IPs

### High Priority Issues

1. **Missing Rate Limiting** - Add rate limits to prevent abuse
2. **No Input Validation** - Validate all user inputs
3. **Weak Password Storage** - Hash passwords with bcrypt/argon2
4. **Missing Security Headers** - Add CSP, HSTS, etc.
5. **Unencrypted Data** - Enable encryption at rest and in transit
6. **No Audit Logging** - Log security events
7. **Open CORS Policy** - Restrict to specific origins
8. **No Resource Limits** - Set K8s resource limits

### Medium Priority Improvements

1. **Generic Error Messages** - Don't expose internals
2. **Structured Logging** - Add context to logs
3. **Metrics Collection** - Add Prometheus metrics
4. **Health Checks** - Implement liveness/readiness probes
5. **Graceful Shutdown** - Handle SIGTERM properly
6. **Connection Timeouts** - Add timeouts to external calls
7. **Retry Logic** - Add retry with exponential backoff
8. **Circuit Breakers** - Prevent cascading failures

## Security Resources

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [Python Security Best Practices](https://python.readthedocs.io/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)
- [Kubernetes Security](https://kubernetes.io/docs/concepts/security/)
- [Docker Security](https://docs.docker.com/engine/security/)
