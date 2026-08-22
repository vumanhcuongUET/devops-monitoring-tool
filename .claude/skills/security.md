# Claude Code Skill: security - Security Analysis & Validation

## Overview

**Skill Name**: `security`
**Purpose**: Security analysis including CSP, headers, secret scanning, and compliance checks
**Trigger**: User requests related to security, CSP, headers, secrets, vulnerabilities
**Version**: 1.0

---

## Skill Definition

```yaml
name: security
description: Security analysis assistant for CSP, headers, secret scanning, and compliance validation
triggers:
  - "security"
  - "csp"
  - "content security policy"
  - "security headers"
  - "secret"
  - "vulnerability"
  - "sast"
  - "csrf"
  - "xss"
  - "https"
  - "tls"
  - "ssl"
examples:
  - "Analyze CSP policy"
  - "Check security headers"
  - "Scan for exposed secrets"
  - "Validate TLS configuration"
```

---

## Capabilities

### 1. Content Security Policy (CSP) Analysis

#### Current Policy Analysis
```yaml
# Input: URL or CSP header value
command: "Analyze the CSP policy for api.example.com"

current_csp: |
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.example.com; img-src * data:; style-src 'self' 'unsafe-inline';

analysis:
  severity_issues:
    - unsafe_inline:
        severity: HIGH
        location: script-src, style-src
        risk: Allows inline scripts/styles (XSS vulnerability)
        fix: Use nonces or hashes instead
        
    - wildcard_source:
        severity: MEDIUM
        location: img-src * data:
        risk: Allows images from any origin
        fix: Specify allowed image domains
        
  recommendations:
    - Remove 'unsafe-inline' from script-src
    - Replace 'unsafe-inline' in style-src with nonces
    - Replace img-src * with specific domains
    - Consider adding report-uri for CSP violations
```

#### CSP Generation
```yaml
# Input: Application requirements
command: "Generate a strict CSP for our React application"

requirements:
  framework: React
  external_scripts:
    - https://cdn.jsdelivr.net/npm/react@18
    - https://www.googletagmanager.com
  styles: Inline (styled-components)
  images: CDN + S3 bucket
  api: https://api.example.com

generated_csp: |
  Content-Security-Policy:
    default-src 'self';
    script-src 'self'
      'nonce-{random}'
      https://cdn.jsdelivr.net
      https://www.googletagmanager.com;
    style-src 'self' 'nonce-{random}';
    img-src 'self'
      https://cdn.example.com
      https://s3.amazonaws.com/my-bucket;
    connect-src 'self' https://api.example.com;
    font-src 'self' https://fonts.googleapis.com;
    object-src 'none';
    base-uri 'self';
    form-action 'self';
    frame-ancestors 'none';
    report-uri /csp-report-endpoint

implementation_notes:
  - Server must generate random nonces per request
  - styled-components will work with nonces
  - Report-only mode recommended for 1-2 weeks first
```

#### CSP Migration Path
```yaml
# Input: Current CSP, target strictness
command: "Create migration plan from permissive to strict CSP"

migration_phases:
  phase_1_report_only:
    duration: 2 weeks
    csp_mode: Report-Only
    header: Content-Security-Policy-Report-Only
    action: Collect violations without blocking
    
  phase_2_warn_level:
    duration: 1 week
    csp_mode: Report-Only + warnings
    action: Notify users of policy changes
    
  phase_3_enforce_partial:
    duration: 2 weeks
    csp_mode: Enforce
    policy: Medium strictness (allow common CDNs)
    
  phase_4_enforce_strict:
    duration: Ongoing
    csp_mode: Enforce
    policy: Strict CSP with nonces only

success_criteria:
  - <10 violations per day in Phase 1
  - Zero user-reported issues in Phase 3
  - All inline scripts converted to nonces
```

---

### 2. Security Headers Validation

#### Header Analysis
```yaml
# Input: URL or deployment config
command: "Validate all security headers for production"

headers_checked:
  Content-Security-Policy:
    status: ✅ Present
    value: default-src 'self'...
    score: A
    
  Strict-Transport-Security:
    status: ✅ Present
    value: max-age=31536000; includeSubDomains; preload
    score: A
    
  X-Frame-Options:
    status: ⚠️ Present (deprecated)
    value: DENY
    recommendation: Replace with frame-ancestors in CSP
    
  X-Content-Type-Options:
    status: ✅ Present
    value: nosniff
    score: A
    
  Permissions-Policy:
    status: ❌ Missing
    recommendation: |
      Add: Permissions-Policy:
        geolocation=(), microphone=(), camera=()
        
  Referrer-Policy:
    status: ⚠️ Default (no-policy)
    value: (browser default)
    recommendation: |
      Add: Referrer-Policy: strict-origin-when-cross-origin
      
  X-XSS-Protection:
    status: ⚠️ Present (deprecated)
    value: 1; mode=block
    recommendation: Remove (modern browsers ignore)

overall_score: B+
missing_headers:
  - Permissions-Policy
  - Referrer-Policy
```

#### Configuration Recommendations
```yaml
# Input: Framework, deployment type
command: "Generate security headers config for FastAPI"

framework: FastAPI
deployment: Production (nginx + kubernetes)

nginx_config: |
    # Security Headers
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'nonce-{random}'; object-src 'none'; base-uri 'self';" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=(), payment=()" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

fastapi_middleware: |
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
    from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware

    # Add HTTPS redirect
    app.add_middleware(HTTPSRedirectMiddleware)

    # Add trusted host
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["api.example.com", ".example.com"]
    )
```

---

### 3. Secret Exposure Scanning

#### Git History Scan
```yaml
# Input: Repository URL, scan depth
command: "Scan git history for exposed secrets"

scan_config:
  repository: /path/to/repo
  depth: 6 months
  branches: [main, develop, feature/*]

scan_results:
  secrets_found: 5
  severity_breakdown:
    critical: 2 (API keys with active permissions)
    high: 1 (Production database password)
    medium: 2 (Deprecated tokens)

findings:
  - file: config/database.py
    commit: a1b2c3d
    date: 2026-06-15
    secret_type: AWS_ACCESS_KEY
    status: ❌ ACTIVE (key still valid!)
    action: Rotate immediately
    
  - file: .env.backup
    commit: e5f6g7h
    date: 2026-05-20
    secret_type: STRIPE_SECRET_KEY
    status: ⚠️ EXPIRED (key rotated)
    action: Remove from history with BFG Repo-Cleaner
    
  - file: k8s/secrets.yaml
    commit: i8j9k0l
    date: 2026-07-01
    secret_type: Base64 encoded value
    status: ✅ False positive (K8s secret)
    action: None

remediation_commands:
  - |
    # Remove secrets from history
    git filter-branch --force --index-filter \
      'git rm --cached --ignore-unmatch config/database.py' \
      --prune-empty --tag-name-filter cat -- --all
```

#### Container Image Scan
```yaml
# Input: Image name
command: "Scan container image for secrets"

image: myapp:latest

scan_layers:
  layer_1_base:
    secrets: 0
    
  layer_2_deps:
    secrets: 0
    
  layer_3_app:
    secrets: 2
    - .env file found (contains DB_PASSWORD)
    - config.json contains API_KEY (weak encoding)

results:
  total_secrets: 2
  risk_level: HIGH
  recommendation: |
    1. Use multi-stage builds to exclude .env
    2. Use build arguments instead of env files
    3. Store secrets in Secret Management (not in image)

dockerfile_recommendation: |
    # DON'T do this:
    COPY .env /app/.env
    
    # DO this instead:
    # Build args for non-sensitive config
    ARG API_ENVIRONMENT
    ENV ENVIRONMENT=$API_ENVIRONMENT
    
    # Secrets mounted at runtime
    # via K8s secrets or docker swarm secrets
```

#### CI/CD Variable Scan
```yaml
# Input: CI platform, repo
command: "Scan GitHub Actions for exposed secrets"

platform: GitHub Actions
scan_results:
  workflow_files: 15
  issues_found: 3

issues:
  - workflow: deploy-production.yml
    issue: API key exposed in logs
    location: step: deploy, run: echo ${{ secrets.API_KEY }}
    fix: Use ::add-mask:: before printing
    
  - workflow: test.yml
    issue: Secret in workflow file (not stored in repo secrets)
    location: env: AWS_ACCESS_KEY: "AKIAIOSFODNN7EXAMPLE"
    fix: Move to GitHub repository settings → Secrets
    
  - workflow: build.yml
    issue: Docker login token in logs
    location: step: docker-login, password: ${{ secrets.DOCKER_PASSWORD }}
    fix: Add @actions/core::setSecret to mask token

best_practices:
  - Never log secret values
  - Use ::add-mask:: (GitHub) or mask_token (GitLab)
  - Rotate any leaked secrets immediately
  - Enable secret scanning in repo settings
```

---

### 4. Security Compliance Scoring

#### Overall Security Score
```yaml
# Input: URL or config files
command: "Calculate security compliance score"

scoring_categories:
  headers: 25%
  csp: 25%
  tls: 20%
  secrets: 15%
  dependencies: 15%

scores:
  security_headers: 80/100
    - Missing: Permissions-Policy, Referrer-Policy
  content_security_policy: 60/100
    - Has 'unsafe-inline' (HIGH risk)
  tls_ssl: 90/100
    - TLS 1.3, strong ciphers
  secret_exposure: 70/100
    - 1 secret found in git history (rotated)
  dependency_vulnerabilities: 85/100
    - 2 medium CVEs in deps

overall_score: 76/100 (B)

grade_scale:
  90-100: A (Excellent)
  80-89: B (Good)
  70-79: C (Acceptable)
  60-69: D (Needs Improvement)
  <60: F (Critical)

priority_fixes:
  1. Remove 'unsafe-inline' from CSP (+15 points)
  2. Add Permissions-Policy header (+5 points)
  3. Update dependencies with CVEs (+10 points)
  4. Add Referrer-Policy header (+5 points)

potential_score: 91/100 (A) after fixes
```

---

## Integration with Claude Code

### File Context Awareness

The skill should:
1. **Read CSP configurations** in backend/frontend code
2. **Scan nginx configs** for security headers
3. **Check git history** for exposed secrets
4. **Analyze Dockerfiles** for secret patterns
5. **Review CI/CD workflows** for secret exposure

### Tool Usage

```python
# Tools the skill should use:
- Bash: gitleaks, trufflehog, git commands
- Read: Config files, Dockerfiles, workflow files
- WebFetch: SSL Labs API, security headers check
```

---

## Examples

### Example 1: CSP Analysis
```
User: Is our CSP secure enough for production?

Claude:
I'll analyze your CSP configuration for security issues.

[Reads CSP from code/headers]

Analysis: Current CSP Rating: C (Issues Found)

❌ HIGH: 'unsafe-inline' in script-src allows XSS attacks
⚠️ MEDIUM: Wildcard in img-src allows images from any origin
✅ GOOD: object-src 'none' prevents plugin execution

Recommendation:
1. Remove 'unsafe-inline' and use nonces
2. Replace img-src * with specific domains
3. Add report-uri to monitor violations

I can generate a production-ready CSP if you'd like.
```

### Example 2: Secret Scan
```
User: Scan our repo for any exposed secrets

Claude:
I'll scan the git history for potential secret exposure.

[Runs gitleaks]

⚠️ 3 potential secrets found:

1. API Key in config/database.py (commit a1b2c3d - 2026-06-15)
   Status: ❌ ACTIVE - Key still has permissions!
   Action: Rotate immediately

2. AWS Secret Key in .env.backup (commit e5f6g7h)
   Status: ✅ EXPIRED - Key already rotated
   Action: Remove from git history

3. Base64 string in k8s/secrets.yaml
   Status: ✅ False positive (K8s secret)
   Action: None

Would you like me to generate the git commands to remove these from history?
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-22 | Initial skill definition |

---

## Dependencies

### Required Tools
- `gitleaks` - Secret scanning (optional)
- `trufflehog` - Secret scanning (optional)
- `nginx` - For header validation (optional)

### Python Libraries
```python
import re
import subprocess
import requests
from urllib.parse import urlparse
```

---

## Related Skills

- **`k8s`** - For Kubernetes security contexts and policies
- **`observability`** - For security-related metrics and alerts

---

**Skill Type**: Security/Validation
**Confidence**: High
**Production Ready**: Yes
