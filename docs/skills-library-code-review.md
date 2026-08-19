# Code Review Skills - Comprehensive Analysis

## Current Skills (Available)
✅ `code_dependency_audit` - Audit dependencies for vulnerabilities
✅ `security_vulnerability_scanner` - Container image scanning
✅ `security_secret_scanner` - Hardcoded secrets detection

## Missing Skills Needed for Complete Code Review

### 1. Code Quality Skills (HIGH PRIORITY)

#### `code_complexity_analyzer` ⭐⭐⭐
**Mục tiêu**: Đo độ phức tạp code (cyclomatic complexity, cognitive complexity)
- Phân tích độ phức tạp của từng function/class
- Flag functions quá phức tạp (>15 complexity)
- Đề xuất refactoring targets
- Tích hợp: SonarQube, CodeClimate, radon (Python)

```python
# Output example
{
  "file": "app/services/api.py",
  "complexity": {
    "cyclomatic": 45,  # HIGH
    "cognitive": 38,
    "nesting_depth": 6
  },
  "complex_functions": [
    {"name": "process_data", "line": 120, "complexity": 15}
  ]
}
```

#### `code_smell_detector` ⭐⭐⭐
**Mục tiêu**: Detect code smells và anti-patterns
- God class, Long method, Feature envy
- Duplicate code, Dead code
- Global variables, Magic numbers
- Inappropriate intimacy

```python
# Code smells detected
{
  "smells": [
    {"type": "god_class", "class": "OrderManager", "reason": "2000 lines, 50 methods"},
    {"type": "long_method", "function": "process_order", "lines": 250},
    {"type": "duplicate_code", "duplication_rate": "15%"}
  ]
}
```

#### `code_style_checker` ⭐⭐
**Mục tiêu**: Check coding style và conventions
- Python: PEP8 compliance (pylint, flake8, black)
- TypeScript/JavaScript: ESLint, Prettier
- Go: gofmt, golint
- Custom style rules enforcement

#### `code_duplication_detector` ⭐⭐⭐
**Mục tiêu**: Tìm code trùng lặp
- Clone detection (type-1, type-2, type-3 clones)
- Similar code blocks >10 lines
- Suggest extraction to functions
- Tích hợp: SonarQube, PMD-CPD

#### `code_test_coverage_analyzer` ⭐⭐⭐
**Mục tiêu**: Phân tích độ phủ test
- Line coverage, branch coverage, path coverage
- Uncovered code paths
- Missing edge cases
- Tích hợp: pytest-cov, jest --coverage, coverage.py

#### `code_dead_code_detector` ⭐
**Mục tiêu**: Tìm code không được sử dụng
- Unused imports, functions, variables
- Dead branches after refactoring
- Unreachable code

---

### 2. Security Skills (HIGH PRIORITY - CRITICAL)

#### `code_sast_scanner` ⭐⭐⭐
**Mục tiêu**: Static Application Security Testing
- SQL Injection, XSS, CSRF detection
- Insecure deserialization
- Path traversal, Command injection
- Cryptographic issues
- Tích hợp: Semgrep, CodeQL, Bandit (Python), ESLint Security

```python
# Security issues found
{
  "vulnerabilities": [
    {
      "type": "sql_injection",
      "file": "app/db.py",
      "line": 45,
      "severity": "HIGH",
      "code": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")"
    },
    {
      "type": "hardcoded_secret",
      "file": "app/config.py",
      "line": 12,
      "severity": "CRITICAL",
      "code": "API_KEY = \"sk-1234567890\""
    }
  ]
}
```

#### `security_misconfiguration_detector` ⭐⭐⭐
**Mục tiêu**: Detect security misconfigurations
- Insecure TLS/SSL configurations
- Debug mode enabled in production
- Exposed admin panels
- CORS misconfigurations
- Missing security headers

#### `security_dependency_confusion` ⭐⭐
**Mục tiêu**: Detect dependency confusion attacks
- Internal package names on public registries
- Typosquatting detection
- Supply chain vulnerabilities

---

### 3. DevOps Skills (HIGH PRIORITY)

#### `cicd_pipeline_analyzer` ⭐⭐⭐
**Mục tiêu**: Analyze CI/CD pipeline quality
- Pipeline performance bottlenecks
- Missing security checks
- Broken build dependencies
- Deployment risks
- Compliance violations

```yaml
# Pipeline analysis
{
  "pipeline": ".github/workflows/deploy.yml",
  "issues": [
    {"type": "missing_security_scan", "stage": "build"},
    {"type": "no_tests", "stage": "test"},
    {"type": "auto_deploy_to_prod", "risk": "CRITICAL"}
  ],
  "recommendations": [
    "Add SAST scan before build",
    "Require manual approval for prod deployment"
  ]
}
```

#### `dockerfile_best_practices` ⭐⭐⭐
**Mục tiêu**: Check Dockerfile best practices
- Multi-stage build usage
- Layer optimization
- Security scanning recommendations
- Image size optimization
- Base image vulnerabilities

```python
# Dockerfile analysis
{
  "issues": [
    {"type": "no_multi_stage", "severity": "MEDIUM"},
    {"type": "root_user", "severity": "HIGH"},
    {"type": "large_image", "current_size": "1.2GB"}
  ],
  "recommendations": [
    "Use multi-stage build",
    "Add non-root user",
    "Use alpine base image"
  ]
}
```

#### `kubernetes_manifest_validator` ⭐⭐⭐
**Mục tiêu**: Validate Kubernetes manifests
- Resource limits/requests missing
- Security context misconfigurations
- Liveness/Readiness probe issues
- Label selector problems
- HPA configuration issues

---

### 4. Performance Skills

#### `code_performance_profiler` ⭐⭐
**Mục tiêu**: Profile code for performance issues
- Slow functions identification
- Memory leaks detection
- N+1 query problems
- Inefficient algorithm detection

#### `database_query_analyzer` ⭐⭐
**Mục tiêu**: Analyze database queries in code
- Slow query detection
- N+1 query pattern
- Missing index suggestions
- Query optimization recommendations

---

### 5. Best Practices Skills

#### `git_commit_message_analyzer` ⭐
**Mục tiêu**: Analyze commit message quality
- Conventional commits compliance
- Message clarity and completeness
- Commit size recommendations

#### `pull_request_quality_checker` ⭐⭐
**Mục tiêu**: Check PR quality before merge
- PR size (too large = harder review)
- Missing description
- Missing reviewers
- Linked issues/tickets
- Test coverage requirements

---

## Implementation Priority Matrix

### Critical (Implement First)
1. ✅ `code_sast_scanner` - Security is paramount
2. ✅ `code_complexity_analyzer` - Maintainability
3. ✅ `code_test_coverage_analyzer` - Quality assurance
4. ✅ `dockerfile_best_practices` - Container security
5. ✅ `kubernetes_manifest_validator` - Deployment safety

### High Priority
6. ✅ `code_smell_detector` - Code quality
7. ✅ `code_duplication_detector` - DRY principle
8. ✅ `cicd_pipeline_analyzer` - DevOps excellence
9. ✅ `security_misconfiguration_detector` - Security

### Medium Priority
10. `code_style_checker` - Consistency
11. `code_performance_profiler` - Performance
12. `database_query_analyzer` - Database optimization

### Low Priority
13. `code_dead_code_detector` - Cleanup
14. `git_commit_message_analyzer` - Process
15. `pull_request_quality_checker` - Workflow

---

## Proposed Code Review Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    Code Review Workflow                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. PRE-COMMIT HOOKS (Developer Side)                           │
│     ├─ code_style_checker (fast)                               │
│     ├─ code_complexity_analyzer (fast)                          │
│     └─ security_secret_scanner (fast)                           │
│                                                                  │
│  2. PRE-PUSH / PRE-MERGE                                        │
│     ├─ code_sast_scanner (comprehensive)                       │
│     ├─ code_test_coverage_analyzer                              │
│     ├─ code_duplication_detector                                │
│     └─ dependency_audit                                         │
│                                                                  │
│  3. CI/CD PIPELINE                                              │
│     ├─ dockerfile_best_practices                                │
│     ├─ kubernetes_manifest_validator                            │
│     ├─ cicd_pipeline_analyzer                                   │
│     └─ security_vulnerability_scanner (containers)              │
│                                                                  │
│  4. PRE-DEPLOYMENT                                             │
│     ├─ security_misconfiguration_detector                       │
│     ├─ code_performance_profiler                                │
│     └─ full test suite                                          │
│                                                                  │
│  5. POST-DEPLOYMENT                                            │
│     ├─ monitoring_alert_optimizer                               │
│     ├─ deployment_health_check                                  │
│     └─ runtime_security_monitor                                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Skill Integration Example

```python
# Comprehensive code review skill
class ComprehensiveCodeReviewSkill(BaseSkill):
    """Run comprehensive code review combining multiple skills."""

    async def analyze(self, project: str, parameters: dict):
        results = {}

        # 1. Security
        results["sast"] = await self._run_skill("code_sast_scanner", ...)
        results["secrets"] = await self._run_skill("security_secret_scanner", ...)

        # 2. Quality
        results["complexity"] = await self._run_skill("code_complexity_analyzer", ...)
        results["smells"] = await self._run_skill("code_smell_detector", ...)
        results["duplication"] = await self._run_skill("code_duplication_detector", ...)

        # 3. Testing
        results["coverage"] = await self._run_skill("code_test_coverage_analyzer", ...)

        # 4. DevOps
        results["dockerfile"] = await self._run_skill("dockerfile_best_practices", ...)
        results["k8s"] = await self._run_skill("kubernetes_manifest_validator", ...)

        # Calculate overall score
        score = self._calculate_score(results)

        return AnalysisResult(
            success=True,
            data={"results": results, "score": score},
        )
```

---

## Recommended Tool Integration

| Category | Tools |
|----------|-------|
| **SAST** | Semgrep, CodeQL, SonarQube, Bandit, ESLint Security |
| **Complexity** | SonarQube, CodeClimate, radon, lizard |
| **Duplication** | SonarQube, PMD-CPD, jscpd |
| **Style** | pylint, flake8, black, ESLint, Prettier |
| **Coverage** | pytest-cov, jest --coverage, coverage.py |
| **Docker** | hadolint, docker-slim, trivy |
| **K8s** | kube-score, kube-linter, conftest |
| **CI/CD** - | GitHub Actions scanning, GitLab CI analysis |

---

## Summary

To achieve **comprehensive code review**, you need approximately **15 additional skills** organized into:

1. **Code Quality (6 skills)**: complexity, smells, duplication, style, dead code, coverage
2. **Security (4 skills)**: SAST, misconfiguration, dependency confusion, secrets
3. **DevOps (3 skills)**: CI/CD analyzer, Dockerfile, K8s manifests
4. **Performance (2 skills)**: profiler, DB queries

**Priority**: Implement Security and Critical DevOps skills first, then Quality, then Performance.

These skills would integrate into your existing Phase 3 skills system, providing a complete code quality and security analysis platform.
