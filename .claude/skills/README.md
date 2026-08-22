# Claude Code Security & DevOps Skills

A comprehensive collection of security and DevOps review skills for Claude Code.

## 📁 Skills Directory

### General Security & DevOps

1. **`security-review.md`** - General security vulnerabilities (injection, authentication, secrets)
2. **`devops-review.md`** - DevOps best practices (resilience, observability, operational excellence)
3. **`comprehensive-security-review.md`** - Master skill combining all security & DevOps checks

### Language-Specific Security

4. **`python-security.md`** - Python-specific vulnerabilities (pickle, yaml, subprocess, etc.)
5. **`fastapi-security.md`** - FastAPI-specific security (auth, RBAC, dependencies, etc.)
6. **`react-security.md`** - React/TypeScript security (XSS, secrets, authentication, etc.)

### API & Database Security

7. **`api-security.md`** - REST API security (auth, CORS, rate limiting, etc.)
8. **`database-security.md`** - Database operations security (SQL injection, encryption, etc.)

### Container & Infrastructure Security

9. **`container-security.md`** - Docker/container security (base images, root user, secrets, etc.)
10. **`k8s-review.md`** - Kubernetes manifests security (RBAC, network policies, etc.)
11. **`infrastructure-security.md`** - Cloud infrastructure (Terraform, AWS, credentials, etc.)

## 🚀 How to Use

### Option 1: Automatic (Recommended)

The skills are automatically loaded by Claude Code when reviewing code. Just mention that you want a security review:

```
"Review this code for security issues"
"Do a security review of the changes"
"Check for security vulnerabilities"
```

### Option 2: Manual Invocation

Invoke specific skills:

```
"Use python-security skill to review this file"
"Run k8s-review on these manifests"
"Apply fastapi-security to check this API"
```

### Option 3: Comprehensive Review

For a complete security and DevOps review:

```
"Do a comprehensive security review of all changes"
"Run comprehensive-security-review on this PR"
"Review for security and DevOps best practices"
```

## 🎯 What These Skills Check

### Security Vulnerabilities

- **Injection**: SQL, command, template, format string
- **Authentication**: Missing auth, weak auth, broken auth
- **Authorization**: IDOR, RBAC bypass, privilege escalation
- **Secrets Management**: Hardcoded secrets, secrets in code
- **Input Validation**: Missing validation, path traversal
- **Cryptography**: Weak encryption, hardcoded keys
- **Logging**: Sensitive data in logs, information disclosure
- **Dependencies**: Vulnerable packages, outdated dependencies
- **Configuration**: Security headers, CORS, CSP

### DevOps Best Practices

- **Error Handling**: Timeouts, retries, circuit breakers
- **Resource Management**: Leaks, cleanup, context managers
- **Observability**: Structured logging, metrics, tracing
- **Reliability**: Health checks, graceful degradation, fallbacks
- **Configuration**: Externalized config, environment-specific
- **Rate Limiting**: Prevent abuse, throttling
- **Deployment**: Safe rollouts, blue-green, canary
- **Monitoring**: SLO/SLI tracking, alerting

### Container Security

- **Images**: Minimal, up-to-date, signed
- **Runtime**: Non-root, no privileges, resource limits
- **Network**: Security groups, network policies
- **Secrets**: Not in images, mounted securely

### Infrastructure Security

- **Credentials**: No hardcoded, from secrets manager
- **Access**: Least privilege, MFA, restricted
- **Encryption**: At rest, in transit
- **Logging**: CloudTrail, audit, monitoring
- **High Availability**: Multi-AZ, backups, replication

## 📊 Coverage Matrix

| Technology | Security Skills | DevOps Skills | Total |
|------------|----------------|----------------|-------|
| **Python** | ✅ python-security, fastapi-security | ✅ devops-review | 3 |
| **Frontend** | ✅ react-security | ✅ devops-review | 2 |
| **API** | ✅ api-security | ✅ devops-review | 2 |
| **Database** | ✅ database-security | ✅ devops-review | 2 |
| **Docker** | ✅ container-security | ✅ devops-review | 2 |
| **Kubernetes** | ✅ k8s-review | ✅ devops-review | 2 |
| **Infrastructure** | ✅ infrastructure-security | ✅ devops-review | 2 |
| **General** | ✅ security-review | ✅ devops-review | 3 |

## 🎓 Learning Resources

These skills also serve as learning resources:

- **Good Examples** - Each skill shows ✅ secure patterns
- **Bad Examples** - Each skill shows ❌ vulnerable patterns
- **Explanations** - Detailed reasoning for each finding
- **Recommendations** - Specific remediation steps

## 🔧 Customization

You can customize these skills for your project:

1. Add project-specific checks
2. Adjust severity thresholds
3. Add custom remediation steps
4. Include team-specific patterns

## 📝 Contributing

To add new skills or improve existing ones:

1. Create `.md` file in `.claude/skills/`
2. Follow the format of existing skills
3. Add clear examples (good/bad)
4. Include checklists and output format
5. Update this README

## 🎉 Summary

**Total Skills Created**: 11 security + DevOps skills

These skills provide comprehensive coverage for:
- ✅ Python/FastAPI backend development
- ✅ React/TypeScript frontend development
- ✅ REST API design and implementation
- ✅ Database operations and queries
- ✅ Docker and container security
- ✅ Kubernetes manifests
- ✅ Cloud infrastructure (Terraform, AWS, etc.)
- ✅ General security best practices
- ✅ DevOps operational excellence

## 🚦 Severity Levels

Skills categorize findings by severity:

- **🔴 Critical** - Immediate security vulnerabilities, must fix now
- **🟠 High** - Important security issues, fix soon
- **🟡 Medium** - Security best practices, should fix
- **🟢 Low** - Minor improvements, nice to have

## 📚 Additional Skills

The directory also contains project-specific development skills:

- `build-frontend.md` - Build frontend
- `check-types.md` - Type checking
- `devops-deploy.md` - Deploy application
- `devops-logs.md` - Check logs
- `devops-status.md` - Check deployment status
- `docs-update.md` - Update documentation
- `format-code.md` - Format code
- `lint-backend.md` - Lint backend
- `lint-frontend.md` - Lint frontend
- `review-changes.md` - Review code changes
- `run-app.md` - Run application
- `test-backend.md` - Test backend
- `test-frontend.md` - Test frontend

---

## 🌟 Phase 5 Skills (New - 2026-08-22)

### Observability & Performance Skills

14. **`observability.md`** - Metrics, traces, dashboards, anomaly detection
15. **`perf.md`** - Performance analysis, load testing, profiling
16. **`k8s.md`** - Kubernetes & GitOps operations (HPA, ServiceMonitor, manifests)
17. **`reliability.md`** - Scaling analysis, DLQ monitoring, circuit breakers
18. **`security.md`** - CSP analysis, security headers, secret scanning

These skills add specialized capabilities for:
- ✅ Kubernetes operations and GitOps workflows
- ✅ Performance profiling and bottleneck detection
- ✅ Observability metrics and distributed tracing
- ✅ Reliability analysis (HPA, DLQ, circuit breakers)
- ✅ Advanced security analysis (CSP, headers, secrets)

**Total Skills**: 18 (11 security/DevOps + 7 development + 5 Phase 5)

---

**Last Updated**: 2026-08-22
**Version**: 1.1.0
**Maintainer**: DevOps Team
