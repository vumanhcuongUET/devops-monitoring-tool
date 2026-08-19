# Skills Library Catalog - Complete Skill List

## Skill Categories

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SKILL LIBRARY SYSTEM                          │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │   DEVOPS        │  │   CODE          │  │   SECURITY      │        │
│  │   Skills        │  │   Skills        │  │   Skills        │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │   FINOPS        │  │   CAPACITY       │  │   MONITORING    │        │
│  │   Skills        │  │   Skills        │  │   Skills        │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │   INCIDENT      │  │   RELIABILITY    │  │   COMPLIANCE     │        │
│  │   Skills        │  │   Skills        │  │   Skills        │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. DEVOPS SKILLS

### 1.1 Deployment Skills

#### `devops_deployment_health_check`
**Mô tả**: Kiểm tra health status của deployments
**Input**: Project name, deployment names
**Output**: Health status, rollback recommendations
**Actions**:
- `kubectl rollout status deployment/<name>`
- `kubectl get pods -l app=<app> -o wide`
- Suggest rollback if health check fails

#### `devops_deployment_rollback`
**Mô tả**: Rollback deployment về version trước
**Input**: Deployment name, namespace
**Output**: Rollback plan, impact assessment
**Actions**:
- `kubectl rollout history deployment/<name>`
- `kubectl rollout undo deployment/<name>`
- Verify rollback success

#### `devops_deployment_canary_analysis`
**Mô tả**: Phân tích canary deployment results
**Input**: Canary deployment name, metrics threshold
**Output**: Canary analysis report, promote/rollback decision
**Actions**:
- Compare metrics between stable and canary
- Promote canary if success rate > threshold
- Rollback canary if error rate spikes

#### `devops_helm_release_manager`
**Mô tả**: Quản lý Helm releases
**Input**: Release name, namespace
**Output**: Release status, upgrade recommendations
**Actions**:
- `helm list -n <namespace>`
- `helm status <release> -n <namespace>`
- `helm upgrade <release> <chart> -n <namespace>`
- `helm rollback <release> -n <namespace>`

#### `devops_argocd_sync_manager`
**Mô tả**: Quản lý ArgoCD application sync
**Input**: Application name
**Output**: Sync status, out-of-sync resources
**Actions**:
- `argocd app get <app-name>`
- `argocd app sync <app-name>`
- `argocd app diff <app-name>`

### 1.2 Configuration Skills

#### `devops_config_drift_detector`
**Mô tả**: Phát hiện config drift giữa environments
**Input**: Project, environments to compare
**Output**: Drift report, sync recommendations
**Actions**:
- Compare ConfigMaps across namespaces
- Compare Secrets (metadata only)
- Generate sync manifests

#### `devops_config_validator`
**Mô tả**: Validate application configurations
**Input**: Config files, schema definitions
**Output**: Validation errors, fixes
**Actions**:
- Validate YAML syntax
- Check required fields
- Verify environment variable references

#### `devops_env_variable_auditor`
**Mô tả**: Audit environment variables for security issues
**Input**: Deployment configs
**Output**: Secrets detected, recommendations
**Actions**:
- Detect hardcoded secrets
- Flag sensitive data in ConfigMaps
- Recommend moving to Secret Manager

### 1.3 Infrastructure Skills

#### `devops_resource_optimizer`
**Mô tả**: Optimize Kubernetes resource requests/limits
**Input**: Deployment configs, utilization metrics
**Output**: Resource optimization recommendations
**Actions**:
- Analyze actual vs requested resources
- Generate updated resource specs
- `kubectl apply -f optimized-resources.yaml`

#### `devops_hpa_analyzer`
**Mô tả**: Analyze Horizontal Pod Autoscaler effectiveness
**Input**: HPA configs, metrics
**Output**: HPA tuning recommendations
**Actions**:
- `kubectl get hpa -n <namespace>`
- Analyze scaling patterns
- Suggest min/max replicas adjustments

#### `devops_pvc_analyzer`
**Mô tả**: Analyze Persistent Volume Claims usage
**Input**: Namespace
**Output**: Storage optimization recommendations
**Actions**:
- `kubectl get pvc -n <namespace>`
- Identify unused/underutilized PVCs
- Recommend size adjustments

### 1.4 Networking Skills

#### `devops_ingress_analyzer`
**Mô tả**: Analyze Ingress configurations
**Input**: Ingress configs
**Output**: Security and reliability recommendations
**Actions**:
- Check for TLS/SSL certificates
- Validate routing rules
- Detect potential routing conflicts

#### `devops_service_connectivity`
**Mô tả**: Test service connectivity
**Input**: Source service, destination service
**Output**: Connectivity report, issues found
**Actions**:
- `kubectl run test-pod --image=nicolaka/netshoot`
- Test DNS resolution
- Test TCP connectivity

#### `devops_network_policy_auditor`
**Mô tả**: Audit network policies
**Input**: Network policy configs
**Output**: Security gaps, recommendations
**Actions**:
- Find pods without network policy coverage
- Detect overly permissive policies
- Generate policy suggestions

### 1.5 CI/CD Skills

#### `devops_pipeline_failure_analyzer`
**Mô tả**: Analyze CI/CD pipeline failures
**Input**: Pipeline run ID, logs
**Output**: Root cause, fix recommendations
**Actions**:
- Parse pipeline logs
- Identify failure patterns
- Suggest configuration fixes

#### `devops_build_optimization`
**Mô tả**: Analyze and optimize build times
**Input**: Build configs, build history
**Output**: Optimization recommendations
**Actions**:
- Identify slow build steps
- Suggest caching strategies
- Recommend parallel execution

---

## 2. CODE SKILLS

### 2.1 Code Quality Skills

#### `code_complexity_analyzer`
**Mô tả**: Analyze code complexity
**Input**: Repository, branch
**Output**: Complexity report, refactoring targets
**Data Sources**: GitHub/GitLab API, SonarQube
**Actions**:
- Calculate cyclomatic complexity
- Identify complex functions
- Suggest refactoring opportunities

#### `code_smell_detector`
**Mô tả**: Detect code smells and anti-patterns
**Input**: Repository, language
**Output**: Code smell report
**Data Sources**: Static analysis tools (ESLint, PyLint)
**Actions**:
- Detect duplicate code
- Find long methods/functions
- Identify god classes

#### `code_coverage_analyzer`
**Mô tả**: Analyze test coverage
**Input**: Repository, coverage reports
**Output**: Coverage gaps, recommendations
**Actions**:
- Parse coverage reports
- Identify untested code paths
- Suggest test priorities

### 2.2 Dependency Skills

#### `code_dependency_audit`
**Mô tả**: Audit dependencies for vulnerabilities and updates
**Input**: Repository, dependency files
**Output**: Vulnerability report, update recommendations
**Data Sources**: Snyk, Dependabot, npm audit, cargo audit
**Actions**:
- Check for vulnerable dependencies
- Identify outdated packages
- Generate update PRs

#### `code_license_checker`
**Mô tả**: Check license compliance
**Input**: Repository, dependency tree
**Output**: License report, compliance issues
**Actions**:
- Extract license information
- Check against approved license list
- Flag non-compliant dependencies

#### `code_dependency_graph`
**Mô tả**: Build and analyze dependency graph
**Input**: Repository
**Output**: Dependency graph visualization, circular deps
**Actions**:
- Build dependency tree
- Detect circular dependencies
- Identify coupling issues

### 2.3 Performance Skills

#### `code_performance_profiler`
**Mô tả**: Profile code for performance issues
**Input**: Repository, profiling data
**Output**: Performance bottlenecks, optimization targets
**Actions**:
- Analyze profiling results
- Identify slow functions
- Suggest optimization strategies

#### `code_memory_analyzer`
**Mô tả**: Analyze memory usage patterns
**Input**: Repository, memory profiles
**Output**: Memory leaks, optimization opportunities
**Actions**:
- Detect memory leaks
- Identify memory hotspots
- Suggest memory optimizations

#### `code_database_query_analyzer`
**Mô tả**: Analyze database queries in code
**Input**: Repository, query logs
**Output**: Slow queries, N+1 problems
**Actions**:
- Parse SQL queries in code
- Detect N+1 query patterns
- Suggest query optimizations

### 2.4 Security Skills

#### `code_secret_scanner`
**Mô tả**: Scan code for hardcoded secrets
**Input**: Repository, branch
**Output**: Secret locations, remediation steps
**Data Sources**: Gitleaks, truffleHog
**Actions**:
- Scan for API keys, passwords
- Check .git history for secrets
- Generate remediation recommendations

#### `code_sast_scanner`
**Mô tả**: Static Application Security Testing
**Input**: Repository, language
**Output**: Security vulnerabilities, fixes
**Data Sources**: Semgrep, CodeQL, Bandit
**Actions**:
- Run SAST scans
- Detect SQL injection, XSS, etc.
- Generate fix recommendations

#### `code_dependency_confusion`
**Mô tả**: Detect dependency confusion attacks
**Input**: Repository, package names
**Output**: Vulnerable packages, mitigation
**Actions**:
- Check for internal package names on public registries
- Verify package integrity
- Suggest scoped packages

### 2.5 Testing Skills

#### `code_test_generator`
**Mô tả**: Generate test cases from code
**Input**: Repository, functions to test
**Output**: Generated test cases
**Actions**:
- Analyze function signatures
- Generate unit test skeletons
- Suggest test cases based on logic

#### `code_mutation_testing`
**Mô tả**: Analyze test quality with mutation testing
**Input**: Repository, test suite
**Output**: Mutation score, weak tests
**Actions**:
- Run mutation tests
- Identify weak test cases
- Suggest test improvements

---

## 3. SECURITY SKILLS

### 3.1 Vulnerability Management

#### `security_vulnerability_scanner`
**Mô tả**: Scan for vulnerabilities in images and code
**Input**: Container images, repository
**Output**: CVE report, remediation priorities
**Data Sources**: Trivy, Clair, Grype
**Actions**:
- `trivy image <image>`
- `trivy repo <repo-url>`
- Generate patch recommendations

#### `security_cve_tracker`
**Mô tả**: Track CVEs relevant to the stack
**Input**: Technology stack, versions
**Output**: Relevant CVEs, priority patches
**Data Sources**: NVD, CVE databases
**Actions**:
- Monitor CVE feeds
- Filter by technology stack
- Prioritize by severity and exploitability

#### `security_exploit_checker`
**Mô tả**: Check for known exploits
**Input**: CVE list, stack
**Output**: Active exploits, urgency level
**Data Sources**: CISA KEV, ExploitDB
**Actions**:
- Check if CVEs have known exploits
- Prioritize patches for exploitable CVEs
- Alert on critical threats

### 3.2 Configuration Security

#### `security_kube_bench`
**Mô tả**: Kubernetes cluster hardening checks
**Input**: Cluster context
**Output**: CIS benchmark compliance, fixes
**Data Sources**: kube-bench
**Actions**:
- `kube-bench --benchmark <version>`
- Generate compliance report
- Suggest remediation commands

#### `security_misconfiguration_detector`
**Mô tả**: Detect security misconfigurations
**Input**: Infrastructure configs, app configs
**Output**: Security issues, fixes
**Actions**:
- Check for insecure defaults
- Verify TLS/SSL configurations
- Audit security headers

#### `security_iam_auditor`
**Mô tả**: Audit IAM permissions and policies
**Input**: Cloud provider configs
**Output**: Over-privileged accounts, recommendations
**Actions**:
- Analyze IAM policies
- Check for privilege escalation risks
- Suggest least-privilege policies

### 3.3 Runtime Security

#### `security_runtime_monitor`
**Mô tả**: Monitor for runtime security events
**Input**: Falco logs, runtime events
**Output**: Security events, alerts
**Data Sources**: Falco
**Actions**:
- Detect suspicious process execution
- Flag file system anomalies
- Alert on network violations

#### `security_container_escape`
**Mô tả**: Detect container escape attempts
**Input**: Syslogs, container logs
**Output**: Escape attempts, mitigation
**Actions**:
- Detect privileged container usage
- Flag sensitive host mounts
- Alert on suspicious syscalls

### 3.4 Secrets Management

#### `security_secrets_audit`
**Mô tả**: Audit secrets management
**Input**: Secret stores, k8s secrets
**Output**: Secret usage, compliance issues
**Actions**:
- Check for secrets in git history
- Audit secret access logs
- Verify secret rotation

#### `security_secret_rotation`
**Mô tả**: Check and enforce secret rotation
**Input**: Secret metadata, rotation policies
**Output**: Stale secrets, rotation schedule
**Actions**:
- Check secret age
- Flag unrotated secrets
- Generate rotation reminders

### 3.5 Compliance

#### `security_compliance_checker`
**Mô tả**: Check compliance frameworks
**Input**: Framework selection (CIS, NIST, SOC2, PCI-DSS)
**Output**: Compliance report, gaps
**Actions**:
- Run compliance checks
- Generate gap analysis
- Suggest remediation

#### `security_data_classification`
**Mô tả**: Classify data by sensitivity
**Input**: Data inventory, access patterns
**Output**: Data classification, protection needs
**Actions**:
- Analyze data access patterns
- Classify by PII/sensitivity
- Recommend encryption/access controls

---

## 4. FINOPS SKILLS

### 4.1 Cost Analysis

#### `finops_cost_analyzer`
**Mô tả**: Analyze cloud costs and trends
**Input**: Time range, cost data
**Output**: Cost breakdown, anomalies
**Data Sources**: CloudWatch Billing, Cost Explorer
**Actions**:
- Analyze cost by service/resource
- Detect cost spikes
- Generate cost forecasts

#### `finops_cost_anomaly_detector`
**Mô tả**: Detect unusual cost patterns
**Input**: Cost history
**Output**: Anomalies, root causes
**Actions**:
- Identify unexpected cost increases
- Correlate with resource changes
- Alert on budget overruns

#### `finops_reserved_instance_planner`
**Mô tả**: Plan reserved instance purchases
**Input**: Usage patterns
**Output**: RI recommendations, savings estimates
**Actions**:
- Analyze instance usage patterns
- Recommend RIs vs On-Demand
- Calculate savings potential

### 4.2 Resource Optimization

#### `finops_rightsizing`
**Mô tả**: Right-size resources based on actual usage
**Input**: Resource metrics, current specs
**Output**: Rightsizing recommendations
**Actions**:
- Analyze CPU/memory utilization
- Recommend instance type changes
- Generate resize commands

#### `finops_idle_resources`
**Mô tả**: Find idle or underutilized resources
**Input**: Resource inventory, metrics
**Output**: Idle resources, deletion candidates
**Actions**:
- Identify unused instances
- Find idle volumes
- Suggest cleanup actions

#### `finops_unattached_resources`
**Mô tả**: Find unattached resources (EIPs, EBS, etc.)
**Input**: Resource inventory
**Output**: Unattached resources, cleanup costs
**Actions**:
- Find unattached EIPs
- Find unattached EBS volumes
- Calculate potential savings

### 4.3 Scheduling

#### `finops_scheduling_optimizer`
**Mô tả**: Optimize resource scheduling
**Input**: Workload patterns
**Output**: Schedule recommendations
**Actions**:
- Analyze workload time patterns
- Suggest start/stop schedules
- Generate auto-scaling rules

---

## 5. CAPACITY PLANNING SKILLS

### 5.1 Resource Forecasting

#### `capacity_planner`
**Mô tả**: Plan capacity based on trends
**Input**: Historical metrics, growth projections
**Output**: Capacity forecast, scaling plan
**Actions**:
- Analyze utilization trends
- Forecast resource needs
- Generate scaling recommendations

#### `capacity_growth_predictor`
**Mô tả**: Predict resource growth
**Input**: Historical data, seasonality
**Output**: Growth predictions
**Actions**:
- Detect growth patterns
- Account for seasonality
- Predict Q3/Q4 needs

### 5.2 Bottleneck Analysis

#### `capacity_bottleneck_detector`
**Mô tả**: Detect performance bottlenecks
**Input**: Metrics, traces
**Output**: Bottleneck report, fixes
**Actions**:
- Analyze resource contention
- Identify CPU/memory bottlenecks
- Suggest scaling strategies

#### `capacity_dependency_mapper`
**Mô tả**: Map service dependencies for capacity
**Input**: Service graph, metrics
**Output**: Dependency capacity report
**Actions**:
- Map upstream/downstream dependencies
- Calculate cascading capacity needs
- Plan for headroom

---

## 6. MONITORING SKILLS

### 6.1 Alerting

#### `monitoring_alert_optimizer`
**Mô tả**: Optimize alert rules
**Input**: Alert history, metrics
**Output**: Alert tuning recommendations
**Actions**:
- Analyze alert fatigue
- Suggest threshold adjustments
- Recommend alert consolidation

#### `monitoring_silence_manager`
**Mô tả**: Manage alert silences intelligently
**Input**: Alert patterns, maintenance schedules
**Output**: Silence recommendations
**Actions**:
- Suggest silences for maintenance
- Auto-silence known flapping alerts
- Aggregate related alerts

### 6.2 Observability

#### `monitoring_dashboard_auditor`
**Mô tả**: Audit dashboard completeness
**Input**: Dashboard configs, SLIs
**Output**: Coverage gaps, dashboard suggestions
**Actions**:
- Check if SLIs are monitored
- Identify missing dashboards
- Suggest new panels

#### `monitoring_sli_calculator`
**Mô tả**: Calculate and track SLIs
**Input**: Service configs, metrics
**Output**: SLI values, SLO status
**Actions**:
- Calculate error budgets
- Track SLO compliance
- Alert on SLO breaches

---

## 7. INCIDENT MANAGEMENT SKILLS

### 7.1 Incident Response

#### `incident_root_cause_analyzer`
**Mô tả**: Analyze incidents for root causes
**Input**: Incident data, logs, metrics
**Output**: Root cause analysis, patterns
**Actions**:
- Correlate incidents with changes
- Identify common failure modes
- Generate postmortem insights

#### `incident_runbook_executor`
**Mô tả**: Execute runbook procedures
**Input**: Runbook ID, incident context
**Output**: Execution results
**Actions**:
- Execute runbook steps
- Verify each step success
- Rollback on failure

### 7.2 Post-Incident

#### `incident_postmortem_generator`
**Mô tả**: Generate postmortem documents
**Input**: Incident timeline, data
**Output**: Postmortem draft
**Actions**:
- Compile incident timeline
- Extract key learnings
- Generate action items

---

## 8. RELIABILITY SKILLS

### 8.1 Availability

#### `reliability_slo_tracker`
**Mô tả**: Track SLO compliance
**Input**: SLO configs, metrics
**Output**: SLO status, error budget
**Actions**:
- Calculate SLO compliance
- Track error budget remaining
- Alert on budget exhaustion

#### `reliability_sla_compliance`
**Mô tả**: Check SLA compliance
**Input**: SLA terms, SLO data
**Output**: Compliance report, risks
**Actions**:
- Compare SLO vs SLA
- Calculate breach probability
- Suggest mitigation strategies

### 8.2 Resilience

#### `reliability_fault_injection`
**Mô tả**: Plan chaos engineering experiments
**Input**: Service topology
**Output**: Experiment recommendations
**Actions**:
- Suggest failure scenarios
- Design experiment plans
- Measure resilience improvements

#### `reliability_dependency_health`
**Mô tả**: Monitor dependency health
**Input**: Service dependencies, health checks
**Output**: Dependency health report
**Actions**:
- Track upstream/downstream health
- Detect cascading failures
- Alert on dependency degradation

---

## 9. COMPLIANCE SKILLS

### 9.1 Regulatory Compliance

#### `compliance_gdpr_auditor`
**Mô tả**: Audit GDPR compliance
**Input**: Data inventory, processing activities
**Output**: GDPR compliance report
**Actions**:
- Check data processing consent
- Verify data retention policies
- Audit data subject requests

#### `compliance_soc2_checker`
**Mô tả**: Check SOC2 controls
**Input**: Control framework, evidence
**Output**: SOC2 compliance status
**Actions**:
- Verify access controls
- Check change management
- Audit incident response

### 9.2 Internal Policies

#### `compliance_tag_enforcer`
**Mô tả**: Enforce resource tagging policies
**Input**: Resource inventory, tagging policies
**Output**: Compliance violations, fixes
**Actions**:
- Detect untagged resources
- Enforce required tags
- Auto-tag resources

---

## Skill Priority Matrix

### High Priority (Phase 3A - Weeks 1-4)
- `security_vulnerability_scanner`
- `security_secret_scanner`
- `finops_cost_analyzer`
- `finops_idle_resources`
- `devops_deployment_health_check`
- `devops_resource_optimizer`
- `code_dependency_audit`
- `code_secret_scanner`

### Medium Priority (Phase 3B - Weeks 5-6)
- `security_kube_bench`
- `security_misconfiguration_detector`
- `finops_rightsizing`
- `capacity_planner`
- `monitoring_alert_optimizer`
- `reliability_slo_tracker`
- `devops_config_drift_detector`

### Low Priority (Phase 3C - Weeks 7-8)
- `compliance_*` skills
- `code_*` advanced skills
- `incident_*` skills
- Advanced finops skills

---

## Skill Implementation Order

### Sprint 1 (Weeks 1-2): Core Security & Cost
1. `security_vulnerability_scanner`
2. `security_secret_scanner`
3. `finops_cost_analyzer`
4. `finops_idle_resources`

### Sprint 2 (Weeks 3-4): DevOps Fundamentals
5. `devops_deployment_health_check`
6. `devops_resource_optimizer`
7. `devops_config_drift_detector`
8. `code_dependency_audit`

### Sprint 3 (Weeks 5-6): Advanced Security & FinOps
9. `security_kube_bench`
10. `security_misconfiguration_detector`
11. `finops_rightsizing`
12. `capacity_planner`

### Sprint 4 (Weeks 7-8): Monitoring & Reliability
13. `monitoring_alert_optimizer`
14. `reliability_slo_tracker`
15. `devops_hpa_analyzer`
16. `monitoring_sli_calculator`

---

## Configuration Template

```yaml
# config/skills/catalog.yaml

skills:
  # Security
  security_vulnerability_scanner:
    enabled: true
    priority: high
    projects:
      - meinvoice
    schedule: "0 2 * * *"  # Daily at 2 AM
    parameters:
      severity_threshold: "high"
      image_scan: true

  # FinOps
  finops_cost_analyzer:
    enabled: true
    priority: high
    projects:
      - meinvoice
    schedule: "0 9 * * 1"  # Weekly Monday 9 AM
    parameters:
      anomaly_threshold: 20
      forecast_days: 30

  # DevOps
  devops_deployment_health_check:
    enabled: true
    priority: medium
    projects:
      - meinvoice
    schedule: "*/15 * * * *"  # Every 15 minutes
    parameters:
      timeout_seconds: 300

  # Code
  code_dependency_audit:
    enabled: true
    priority: high
    projects:
      - meinvoice
    schedule: "0 10 * * *"  # Daily at 10 AM
    parameters:
      check_transitive: true
      license_check: true
```

---

## API Examples

### Execute Skill

```bash
curl -X POST http://localhost:8000/api/v1/skills/security_vulnerability_scanner/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "project": "meinvoice",
    "parameters": {
      "image": "meinvoice-api:latest",
      "severity_threshold": "high"
    }
  }'
```

### Get Skill Recommendations

```bash
curl http://localhost:8000/api/v1/skills/finops_cost_analyzer/recommendations/analysis-123
```

### List Available Skills

```bash
curl http://localhost:8000/api/v1/skills?category=security&priority=high
```
