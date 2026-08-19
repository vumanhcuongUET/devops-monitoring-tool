# Phase 3 Implementation Plan - Governance & Advanced Skills

## Executive Summary

**Timeline**: 8 weeks (4 sprints × 2 weeks)
**Team Size**: 2-3 developers
**Risk Level**: Medium (involves permission changes and policy enforcement)
**Dependencies**: Phase 2 (Actions System) must be fully operational ✅
**Scope**: 30+ skills across 9 categories (Security, DevOps, Code, FinOps, Capacity, Monitoring, Incident, Reliability, Compliance)

## Implementation Status (as of 2026-08-20)

| Component | Status | Progress | Notes |
|-----------|--------|----------|-------|
| **Phase 2 Security Fixes** | ✅ Complete | 100% | 3 critical vulnerabilities fixed |
| **Skill Library Foundation** | ✅ Complete | 100% | BaseSkill interface, SkillRegistry, 32 skills registered |
| **FinOps Skills** | ✅ Complete | 100% | Cost analyzer, rightsizing, idle resources |
| **Security Skills** | ✅ Complete | 100% | Vuln scanner, compliance, secrets audit, misconfig, runtime monitor |
| **DevOps Skills** | ✅ Complete | 100% | Deployment health, resource optimizer, config drift, CI/CD, Dockerfile, K8s manifests |
| **Code Skills** | ✅ Complete | 100% | Dependency audit, secret scanner, complexity, test coverage, duplication, code smells |
| **Capacity Skills** | ✅ Complete | 100% | Planner, bottleneck detector, growth predictor |
| **RBAC for AI** | ✅ Complete | 100% | Permission matrix, service accounts, Action Engine integration |
| **Policy as Code (OPA)** | ✅ Complete | 100% | OPA client, Rego policies, validation API |
| **Frontend UI** | ✅ Complete | 100% | SkillsPage, GovernanceDashboard |
| **Documentation** | ✅ Complete | 100% | Phase 3 design docs, progress summary |

---

## 📋 Table of Contents

1. [Audit Summary](#audit-summary)
2. [Implementation Phases](#implementation-phases)
3. [Week-by-Week Breakdown](#week-by-week-breakdown)
4. [Critical Path Analysis](#critical-path-analysis)
5. [Risk Mitigation](#risk-mitigation)
6. [Testing Strategy](#testing-strategy)
7. [Rollout Plan](#rollout-plan)

---

## 🔍 Audit Summary

### Phase 1-2 Current State

#### ✅ Completed Components

**Phase 1: Foundation & Observability Copilot**
- ✅ Triage Card generation (`/api/v1/analyze`)
- ✅ LLM Client with Claude integration
- ✅ Context collection from 5 sources (logs, APM, metrics, K8s, alerts)
- ✅ Service clients for Elasticsearch, Prometheus, Kubernetes, APM, SLO
- ✅ Frontend OverviewPage with WebSocket support
- ✅ Comprehensive test coverage

**Phase 2: Human-in-the-loop & Actions**
- ✅ Action Engine (`backend/app/actions/`)
- ✅ Command Parser (`kubectl`, `helm`, `argocd`)
- ✅ Command Validator with RBAC checking
- ✅ Command Executor with safety constraints
- ✅ Approval Store and History
- ✅ Audit Logger with Chain of Thought
- ✅ Context Registry (`backend/app/registry/`)
- ✅ Project configuration system (`projects/*.yaml`)
- ✅ Frontend ActionsPage
- ✅ Actions API endpoints (`/api/v1/actions`)

#### ⚠️ Gaps Identified

1. **No skill system** - All analysis is in LLM client, no modular skill interface
2. **Basic RBAC only** - Environment-based permissions not implemented
3. **No OPA integration** - Policy validation is hardcoded in validator
4. **Limited audit** - No compliance export features
5. **No service account isolation** - Commands execute with default kubeconfig
6. **Rate limiting not implemented** - Only TODO comment in validator

---

## 🚀 Implementation Phases

### Phase 3A: Skill Library (Weeks 1-4)

**Objective**: Build extensible skill system with FinOps, Security, and Capacity Planning skills

**Components**:
```
backend/app/skills/
├── base.py              # BaseSkill interface
├── registry.py          # SkillRegistry
├── __init__.py
├── finops/
│   ├── __init__.py
│   ├── cost_analyzer.py
│   ├── rightsizing.py
│   └── idle_resources.py
├── security/
│   ├── __init__.py
│   ├── vuln_scanner.py
│   ├── compliance.py
│   └── secrets_audit.py
└── capacity/
    ├── __init__.py
    └── planner.py
```

**API Endpoints**:
- `GET /api/v1/skills` - List available skills
- `POST /api/v1/skills/{id}/analyze` - Run skill analysis
- `GET /api/v1/skills/{id}/recommendations/{analysis_id}` - Get recommendations

**Frontend**:
- `SkillsPage.tsx` - Browse and execute skills
- `SkillExecutionPanel.tsx` - Run analysis and view results

### Phase 3B: RBAC for AI (Weeks 3-6)

**Objective**: Implement environment-based AI permissions with service account isolation

**Components**:
```
backend/app/governance/
├── __init__.py
├── ai_rbac.py           # AIPermission enum, ENVIRONMENT_PERMISSIONS
├── permission_checker.py # AIPermissionChecker
└── service_accounts/    # K8s service account manifests
    ├── prod-viewer.yaml
    ├── staging-operator.yaml
    └── dev-admin.yaml
```

**Configuration**:
```yaml
config/ai_service_accounts.yaml
```

**API Endpoints**:
- `POST /api/v1/governance/permissions/check` - Check permission
- `GET /api/v1/governance/service-account/{project}` - Get SA config

### Phase 3C: Policy as Code (Weeks 5-8)

**Objective**: Integrate OPA for policy validation and enforcement

**Components**:
```
policies/opa/
├── actions.rego        # Main action policies
├── resources.rego      # Resource protection policies
└── time_windows.rego   # Business hour restrictions

backend/app/governance/
└── opa_client.py      # OPA API client
```

**Infrastructure**:
- Deploy OPA server (K8s deployment)
- OPA bundle serving

---

## 📅 Week-by-Week Breakdown

### Week 1: Skill Foundation

**Backend**:
- [ ] Create `backend/app/skills/` directory structure
- [ ] Implement `BaseSkill` interface (`skills/base.py`)
- [ ] Implement `SkillRegistry` (`skills/registry.py`)
- [ ] Add skill configuration loading from YAML
- [ ] Unit tests for skill registry

**Frontend**:
- [ ] Create `SkillsPage.tsx` skeleton
- [ ] Add skill navigation to sidebar

**Deliverables**:
- Skill foundation package
- Basic skill listing UI

---

### Week 2: Core Security & FinOps Skills (Sprint 1)

**Backend** (Security):
- [ ] `security_vulnerability_scanner` - Trivy integration
- [ ] `security_secret_scanner` - Gitleaks integration
- [ ] Security skill configurations

**Backend** (FinOps):
- [ ] `finops_cost_analyzer` - Cost Explorer integration
- [ ] `finops_idle_resources` - Resource detection
- [ ] `finops_rightsizing` - Resource optimization
- [ ] FinOps skill configurations

**Frontend**:
- [ ] Add skill execution panel
- [ ] Implement cost visualization
- [ ] Add security recommendation cards

**Deliverables**:
- 2 Security skills
- 3 FinOps skills
- Skill execution UI

---

### Week 3: DevOps Skills + Code Skills (Sprint 1 continued)

**Backend** (DevOps):
- [ ] `devops_deployment_health_check` - Deployment monitoring
- [ ] `devops_resource_optimizer` - Resource tuning
- [ ] `devops_config_drift_detector` - Config validation
- [ ] `devops_helm_release_manager` - Helm operations

**Backend** (Code):
- [ ] `code_dependency_audit` - Dependency security
- [ ] `code_secret_scanner` - Code secret detection
- [ ] Code skill configurations

**Frontend**:
- [ ] DevOps skills UI components
- [ ] Code skills visualization
- [ ] Skill recommendation cards

**Deliverables**:
- 4 DevOps skills
- 2 Code skills
- Skills UI components

---

### Week 4: RBAC Foundation + Capacity Skills (Sprint 2)

**Backend** (RBAC):
- [ ] Implement `ai_rbac.py` with permission matrix
- [ ] Implement `permission_checker.py`
- [ ] Create service account configurations
- [ ] Add permission checking to Action Engine

**Backend** (Capacity):
- [ ] `capacity_planner` - Capacity forecasting
- [ ] `capacity_bottleneck_detector` - Performance analysis
- [ ] `capacity_growth_predictor` - Growth predictions
- [ ] Capacity skill configurations

**Frontend**:
- [ ] RBAC permission matrix UI
- [ ] Capacity planning visualization
- [ ] Complete SkillsPage

**Deliverables**:
- RBAC permission system
- 3 Capacity skills
- Full SkillsPage implementation

---

### Week 5: Advanced Security + Service Account Isolation (Sprint 3)

**Backend** (Advanced Security):
- [ ] `security_kube_bench` - CIS benchmark checks
- [ ] `security_misconfiguration_detector` - Config security
- [ ] `security_runtime_monitor` - Falco integration
- [ ] `security_secrets_audit` - Secret management audit
- [ ] Security skill configurations

**Backend** (Service Accounts):
- [ ] Implement `EnvironmentAwareCommandExecutor`
- [ ] Create K8s service account manifests
- [ ] Implement kubeconfig per environment
- [ ] Add service account rotation logic

**Infrastructure**:
- [ ] Deploy service accounts to clusters
- [ ] Configure RBAC bindings

**Deliverables**:
- 4 Advanced Security skills
- Service account isolation
- Environment-aware execution

---

### Week 6: Monitoring & Reliability + OPA Foundation (Sprint 3 continued)

**Backend** (Monitoring):
- [ ] `monitoring_alert_optimizer` - Alert tuning
- [ ] `monitoring_sli_calculator` - SLI tracking
- [ ] `monitoring_dashboard_auditor` - Dashboard coverage
- [ ] Monitoring skill configurations

**Backend** (Reliability):
- [ ] `reliability_slo_tracker` - SLO compliance
- [ ] `reliability_sla_compliance` - SLA checking
- [ ] `reliability_dependency_health` - Dependency monitoring
- [ ] Reliability skill configurations

**Backend** (OPA):
- [ ] Implement `OPAClient`
- [ ] Write Rego policies for common scenarios

**Deliverables**:
- 3 Monitoring skills
- 3 Reliability skills
- OPA client foundation

---

### Week 7: OPA Integration + Advanced Skills (Sprint 4)

**Backend** (OPA Integration):
- [ ] Deploy OPA server (Docker/K8s)
- [ ] Configure OPA bundle serving
- [ ] Implement policy validation in Action Engine
- [ ] Add policy checking API endpoints
- [ ] Write comprehensive Rego policies

**Backend** (Advanced Skills):
- [ ] `devops_ingress_analyzer` - Ingress security
- [ ] `devops_hpa_analyzer` - HPA optimization
- [ ] `code_sast_scanner` - Static analysis
- [ ] `compliance_gdpr_auditor` - GDPR checks

**Frontend**:
- [ ] Create `GovernanceDashboard.tsx`
- [ ] Add RBAC matrix visualization
- [ ] Add policy status view
- [ ] Implement compliance report UI

**Deliverables**:
- OPA server deployed
- Policy validation integrated
- 4 Advanced skills
- Governance dashboard

---

### Week 8: Testing & Documentation (Sprint 4 completion)

**Testing**:
- [ ] End-to-end integration tests
- [ ] RBAC permission matrix tests
- [ ] OPA policy validation tests
- [ ] Load testing for skill execution
- [ ] Security audit of permissions
- [ ] Skill execution performance tests

**Documentation**:
- [ ] `docs/skills-library-catalog.md` - Complete skill catalog ✅
- [ ] `docs/skills-library.md` - Skill development guide
- [ ] `docs/governance/rbac.md` - RBAC configuration
- [ ] `docs/governance/opa-policies.md` - Policy writing guide
- [ ] Update `CLAUDE.md` with Phase 3
- [ ] Update `docs/chien_luoc_tong_the.md` with Phase 3 status ✅

**Deliverables**:
- Full test coverage
- Complete documentation
- Phase 3 complete ✅

**Deliverables**:
- Full test coverage
- Complete documentation
- Phase 3 complete ✅

---

## ⏱️ Critical Path Analysis

```
Skill Foundation → Core Skills (Sprint 1) → DevOps + Code Skills (Sprint 1)
                                           ↓
RBAC + Capacity (Sprint 2) → Advanced Security + SA (Sprint 3)
                                           ↓
Monitoring + OPA (Sprint 3) → OPA Integration + Advanced (Sprint 4)
                                           ↓
                                    Testing + Documentation (Sprint 4)
```

**Critical Path**: 8 weeks (4 sprints × 2 weeks)

**Parallelization Opportunities**:
- Skills development within each sprint can be done in parallel by different developers
- RBAC and OPA implementation can overlap in Sprint 3
- Frontend and backend work can proceed in parallel after API contracts are defined

---

## 📊 Skills Summary

| Category | Skills Count | Sprint |
|----------|--------------|--------|
| **Security** | 8 | Sprint 1, 3 |
| **FinOps** | 5 | Sprint 1 |
| **DevOps** | 8 | Sprint 1, 4 |
| **Code** | 4 | Sprint 1, 4 |
| **Capacity** | 3 | Sprint 2 |
| **Monitoring** | 3 | Sprint 3 |
| **Reliability** | 3 | Sprint 3 |
| **Compliance** | 2 | Sprint 4 |
| **Incident** | 2 (future) | Phase 4 |
| **TOTAL** | **36+ skills** | - |

**Sprint Distribution**:
- Sprint 1 (Weeks 1-2): 11 skills (Foundation + Core Security + FinOps + Code)
- Sprint 2 (Weeks 3-4): 8 skills (DevOps + RBAC + Capacity)
- Sprint 3 (Weeks 5-6): 10 skills (Advanced Security + Monitoring + Reliability + OPA)
- Sprint 4 (Weeks 7-8): 7 skills (Advanced + Compliance + Testing + Docs)

---

## ⚠️ Risk Mitigation

### Risk 1: Permission Escalation

**Risk**: AI agent gains excessive permissions
**Mitigation**:
- Least privilege service accounts
- Environment-based permission matrix
- Mandatory approval for production actions
- Audit logging for all permission checks

### Risk 2: Policy Overblocking

**Risk**: OPA policies block legitimate operations
**Mitigation**:
- Dry-run mode for policy testing
- Override mechanism with approval
- Phased policy rollout
- Policy review before enforcement

### Risk 3: Service Account Compromise

**Risk**: Service account credentials leaked
**Mitigation**:
- Short-lived tokens (1 hour TTL)
- Rotate credentials regularly
- No persistent storage of credentials
- Audit all SA usage

### Risk 4: Skill Hallucination

**Risk**: Skills generate incorrect recommendations
**Mitigation**:
- Confidence scores for all skill outputs
- Human approval required for all actions
- Skill versioning and rollback
- A/B testing for skill outputs

---

## 🧪 Testing Strategy

### Unit Tests

- Skill interface and registry
- Permission checker logic
- OPA client (mocked)
- Policy validator

### Integration Tests

- End-to-end skill execution
- Permission checking with real projects
- OPA policy evaluation
- Service account command execution

### E2E Tests

- Full workflow: Triage → Skills → Actions → Execute
- Multi-project scenarios
- Policy violation scenarios
- Permission denial scenarios

### Load Tests

- Skill execution under load
- OPA evaluation performance
- Permission check throughput

---

## 🚀 Rollout Plan

### Phase 3A Rollout (Week 4)

1. **Dogfooding** - Run skill system in development environment
2. **Beta Testing** - Enable for staging with select projects
3. **General Availability** - Enable for all non-production projects

### Phase 3B Rollout (Week 5)

1. **Service Accounts** - Deploy to development cluster first
2. **Permission Testing** - Verify permissions in staging
3. **Production** - Deploy with view-only permissions first

### Phase 3C Rollout (Week 6-7)

1. **OPA Dry-Run** - Deploy OPA in audit-only mode
2. **Policy Testing** - Test policies in staging
3. **Gradual Enforcement** - Enable enforcement for non-critical actions
4. **Full Enforcement** - Enable for all actions after validation

---

## 📊 Success Metrics

- **Skill System**: 3+ skills operational, 100+ skill analyses/week
- **RBAC**: 0 permission escalations, 100% audit coverage
- **OPA**: <100ms policy evaluation, 99.9% uptime
- **Overall**: MTTR reduced by 30% vs Phase 2

---

## 🔧 Technical Debt to Address

1. **Rate Limiting** - Implement actual rate limiting in validator
2. **Audit Export** - Add CSV/SOX export functionality
3. **Metrics** - Add Prometheus metrics for skill execution
4. **Caching** - Cache skill analysis results
5. **Error Handling** - Improve error messages for permission/policy failures

---

## 📝 Next Steps

1. **Review this plan** with team and stakeholders
2. **Set up OPA development environment**
3. **Create development service accounts**
4. **Begin Week 1 implementation**
