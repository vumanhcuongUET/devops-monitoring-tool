# Phase 3: Governance & Advanced Skills

## Tổng quan

**Phase 3** mở rộng nền tảng từ Actions System sang **Skill Library** với **Governance** và **Advanced Skills**. Giai đoạn này tập trung vào:
1. **Security Hardening** ✅ - Fix critical security vulnerabilities (HOÀN THÀNH 2026-08-19)
2. **Skill Library** - Hệ thống mở rộng với các kỹ năng chuyên sâu
3. **RBAC for AI** - Phân quyền nghiêm ngặt cho Agent theo environment
4. **Policy as Code** - Tích hợp OPA để kiểm tra policy violations

## Implementation Status (2026-08-19)

| Component | Status | Completion Date |
|-----------|--------|------------------|
| **Security Fixes** | ✅ Complete | 2026-08-19 |
| Command Whitelist Enforcement | ✅ | 2026-08-19 |
| Teams Webhook Authentication | ✅ | 2026-08-19 |
| Authenticated Metrics Endpoint | ✅ | 2026-08-19 |
| **Skill Library** | ⏳ Pending | - |
| BaseSkill Interface | ⏳ | - |
| SkillRegistry | ⏳ | - |
| FinOps Skills | ⏳ | - |
| Security Skills | ⏳ | - |
| **RBAC for AI** | ⏳ Pending | - |
| Permission Matrix | ⏳ | - |
| Service Account Isolation | ⏳ | - |
| **Policy as Code (OPA)** | ⏳ Pending | - |
| OPA Server | ⏳ | - |
| Rego Policies | ⏳ | - |
| **Frontend UI** | ⏳ Pending | - |

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Skill Library System                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   FinOps     │  │   Security   │  │  Capacity    │              │
│  │   Skills     │  │   Skills     │  │  Planning    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│           ┆                 ┆                 ┆                     │
│           └─────────────────┴─────────────────┘                   │
│                              ┆                                      │
│                              ▼                                      │
│                    ┌──────────────────┐                             │
│                    │  Skill Registry  │                             │
│                    │  + Discovery     │                             │
│                    └────────┬─────────┘                             │
└─────────────────────────────────┼───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Governance Layer                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   RBAC for   │  │   Policy     │  │    Audit     │              │
│  │     AI       │  │   as Code    │  │   Logger     │              │
│  │  (per env)   │  │   (OPA)      │  │  (enhanced)  │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Core Action Engine                              │
│              (Phase 2: Create → Validate → Approve → Execute)        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 1. Skill Library System

### 1.1 Skill Interface

Mỗi skill là một module Python độc lập với interface chuẩn:

```python
from app.skills.base import Skill, SkillResult, SkillContext
from app.models.actions import Action

class BaseSkill:
    """Base class for all skills."""

    skill_id: str
    skill_name: str
    skill_type: SkillType  # FINOPS, SECURITY, CAPACITY, OPERATIONS
    version: str = "1.0.0"

    async def analyze(
        self,
        context: SkillContext,
    ) -> SkillResult:
        """Analyze situation and return findings."""
        raise NotImplementedError

    async def recommend_actions(
        self,
        context: SkillContext,
        analysis: SkillResult,
    ) -> list[Action]:
        """Generate actionable recommendations."""
        raise NotImplementedError

    async def execute_action(
        self,
        action: Action,
    ) -> ExecutionResult:
        """Execute a skill-specific action."""
        raise NotImplementedError
```

### 1.2 Skill Registry

Central registry để discover và load skills:

```python
# backend/app/skills/registry.py

class SkillRegistry:
    """Central registry for all available skills."""

    def __init__(self):
        self._skills: dict[str, BaseSkill] = {}
        self._load_builtin_skills()
        self._load_custom_skills()

    def get_skill(self, skill_id: str) -> Optional[BaseSkill]:
        """Get a skill by ID."""
        return self._skills.get(skill_id)

    def list_skills(
        self,
        skill_type: Optional[SkillType] = None,
        environment: Optional[str] = None,
    ) -> list[BaseSkill]:
        """List available skills with optional filters."""

    def register_skill(self, skill: BaseSkill):
        """Register a new skill dynamically."""

    async def analyze_with_skills(
        self,
        context: SkillContext,
        skill_ids: Optional[list[str]] = None,
    ) -> dict[str, SkillResult]:
        """Run analysis using multiple skills in parallel."""
```

### 1.3 Builtin Skills

#### FinOps Skills

```python
# backend/app/skills/finops/cost_analyzer.py

class CostAnalyzerSkill(BaseSkill):
    """Analyze cloud costs and provide optimization recommendations."""

    skill_id = "finops_cost_analyzer"
    skill_name = "Cloud Cost Analyzer"
    skill_type = SkillType.FINOPS

    async def analyze(self, context: SkillContext) -> SkillResult:
        """Analyze cost trends and anomalies."""
        # Query cost data from CloudWatch Billing API / Cost Explorer
        # Identify:
        # - Cost spikes
        # - Over-provisioned resources
        # - Idle resources
        # - Scheduling opportunities

    async def recommend_actions(self, context, analysis) -> list[Action]:
        """Generate cost optimization actions."""
        return [
            Action(
                command="kubectl scale deployment/api --replicas=2 -n meinvoice",
                title="Scale down non-prod environment after hours",
                estimated_savings="$150/month",
            ),
            # ... more recommendations
        ]
```

**Các FinOps skills khác:**
- `finops_rightsizing` - Đề xuất resize instances
- `finops_idle_resources` - Phát hiện idle resources
- `finops_scheduling` - Đề xuất on/off schedule

#### Security Skills

```python
# backend/app/skills/security/vulnerability_scanner.py

class VulnerabilityScannerSkill(BaseSkill):
    """Scan for security vulnerabilities and misconfigurations."""

    skill_id = "security_vuln_scanner"
    skill_name = "Vulnerability Scanner"
    skill_type = SkillType.SECURITY

    async def analyze(self, context: SkillContext) -> SkillResult:
        """Scan for vulnerabilities using integrated tools."""
        # Integrate with:
        # - Trivy for image scanning
        # - Kube-bench for cluster hardening
        # - Falco for runtime security

    async def recommend_actions(self, context, analysis) -> list[Action]:
        """Generate security remediation actions."""
        return [
            Action(
                command="kubectl patch deployment/api -p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":\"api\",\"image\":\"api:patched-v1.2.3\"}]}}}}}'",
                title="Update image to patch CVE-2024-12345",
                severity=SeverityLevel.HIGH,
            ),
        ]
```

**Các Security skills khác:**
- `security_compliance` - Check compliance (CIS, NIST)
- `security_secrets_audit` - Audit secret management
- `security_network_policy` - Analyze network policies

#### Capacity Planning Skills

```python
# backend/app/skills/capacity/planner.py

class CapacityPlannerSkill(BaseSkill):
    """Plan capacity needs based on trends and patterns."""

    skill_id = "capacity_planner"
    skill_name = "Capacity Planner"
    skill_type = SkillType.CAPACITY

    async def analyze(self, context: SkillContext) -> SkillResult:
        """Analyze capacity trends and forecast needs."""
        # Use Prometheus metrics to:
        # - Analyze resource utilization trends
        # - Forecast growth
        # - Identify bottlenecks

    async def recommend_actions(self, context, analysis) -> list[Action]:
        """Generate capacity planning actions."""
        return [
            Action(
                command="kubectl apply -f capacity-plan-q3-2026.yaml",
                title="Apply Q3 capacity plan - scale API to 5 replicas",
                rationale="Projected 30% growth based on current trends",
            ),
        ]
```

### 1.4 Skill Configuration

Skills được cấu hình qua YAML files:

```yaml
# config/skills/finops.yaml
skills:
  - id: finops_cost_analyzer
    enabled: true
    projects:
      - meinvoice
      - another-project
    schedule: "0 9 * * *"  # Daily at 9 AM
    thresholds:
      cost_spike_percent: 20
      idle_days: 7
    notifications:
      - slack: "#finops-alerts"
      - email: "finops-team@example.com"
```

---

## 2. RBAC for AI System

### 2.1 Environment-Based Permissions

Agent permissions được phân chia theo environment:

```python
# backend/app/governance/ai_rbac.py

class AIPermission(Enum):
    """Permissions for AI agents."""
    VIEW = "view"           # Read-only access
    ANALYZE = "analyze"     # Can run analysis
    PROPOSE = "propose"     # Can propose actions
    EXECUTE_SAFE = "execute_safe"  # Can execute SAFE actions only
    EXECUTE_ALL = "execute_all"    # Can execute all approved actions

class Environment(str, Enum):
    """Environments with different risk profiles."""
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TESTING = "testing"

# Permission matrix
ENVIRONMENT_PERMISSIONS: dict[Environment, list[AIPermission]] = {
    Environment.PRODUCTION: [
        AIPermission.VIEW,
        AIPermission.ANALYZE,
        AIPermission.PROPOSE,
    ],
    Environment.STAGING: [
        AIPermission.VIEW,
        AIPermission.ANALYZE,
        AIPermission.PROPOSE,
        AIPermission.EXECUTE_SAFE,
    ],
    Environment.DEVELOPMENT: [
        AIPermission.VIEW,
        AIPermission.ANALYZE,
        AIPermission.PROPOSE,
        AIPermission.EXECUTE_SAFE,
        AIPermission.EXECUTE_ALL,
    ],
    Environment.TESTING: [
        AIPermission.VIEW,
        AIPermission.ANALYZE,
        AIPermission.PROPOSE,
        AIPermission.EXECUTE_ALL,
    ],
}
```

### 2.2 Service Account Isolation

Mỗi environment có service account riêng:

```yaml
# config/ai_service_accounts.yaml
service_accounts:
  production:
    name: "ai-agent-prod-viewer"
    namespace: "ai-agents"
    cluster_role: "view"
    permissions:
      - get
      - list
      - watch
    constraints:
      - no_delete
      - no_modify

  staging:
    name: "ai-agent-staging-operator"
    namespace: "ai-agents"
    cluster_role: "edit"
    permissions:
      - get
      - list
      - watch
      - create
      - update
      - patch
    constraints:
      - no_delete_pvc
      - no_delete_namespace

  development:
    name: "ai-agent-dev-admin"
    namespace: "ai-agents"
    cluster_role: "admin"
    permissions:
      - "*"
    constraints: []
```

### 2.3 Permission Checker

```python
# backend/app/governance/permission_checker.py

class AIPermissionChecker:
    """Check if AI agent has permission for an action."""

    def __init__(self):
        self.registry = get_registry()
        self.env_permissions = ENVIRONMENT_PERMISSIONS
        self.service_accounts = load_service_accounts()

    def check_permission(
        self,
        project: str,
        action: Action,
        permission: AIPermission,
    ) -> tuple[bool, str]:
        """Check if action is allowed for given permission level."""
        # Get project environment
        project_config = self.registry.get_project(project)
        environment = project_config.tags.get("environment", "production")

        # Get allowed permissions for environment
        allowed = self.env_permissions.get(environment, [])
        if permission not in allowed:
            return False, f"Permission {permission} not allowed in {environment}"

        # Check action risk level against permission
        if permission == AIPermission.EXECUTE_SAFE:
            if action.risk_level not in [RiskLevel.SAFE, RiskLevel.LOW]:
                return False, f"Action risk {action.risk_level} exceeds SAFE execution limit"

        return True, "Permission granted"

    def get_service_account(self, project: str) -> dict:
        """Get service account configuration for project."""
        project_config = self.registry.get_project(project)
        environment = project_config.tags.get("environment", "production")
        return self.service_accounts.get(environment)
```

### 2.4 Environment-Aware Command Execution

```python
# Updated executor with environment isolation

class EnvironmentAwareCommandExecutor(CommandExecutor):
    """Execute commands with environment-specific service accounts."""

    async def execute(self, command: str, project: str, **kwargs) -> ExecutionResult:
        """Execute command using appropriate service account."""
        # Get service account for project environment
        sa_config = self.permission_checker.get_service_account(project)

        # Set up kubeconfig for service account
        kubeconfig_path = self._prepare_sa_kubeconfig(sa_config)

        # Execute with service account context
        env = os.environ.copy()
        env["KUBECONFIG"] = kubeconfig_path

        # ... execute with service account isolation
```

---

## 3. Policy as Code (OPA Integration)

### 3.1 OPA Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Policy Enforcement                           │
│                                                                      │
│  ┌──────────────┐      validate      ┌──────────────┐               │
│  │   Action     │ ──────────────────>│    OPA       │               │
│  │   Request    │                    │    Server    │               │
│  └──────────────┘                     └──────┬───────┘               │
│                                              │                        │
│                                              │ decision              │
│                                              ▼                        │
│                                    ┌──────────────────┐             │
│                                    │ allow/deny +     │             │
│                                    │ reasons          │             │
│                                    └──────────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Rego Policies

```rego
# policies/opa/actions.rego

package devops.actions

default allow = false

# Allow read-only actions without approval
allow {
    input.action.risk_level == "safe"
    input.action.command_type == "kubectl"
    is_read_only_action(input.action.parsed_params)
}

# Allow approved actions in staging/development
allow {
    input.environment != "production"
    input.action.status == "approved"
    not forbidden_action(input.action)
}

# Deny actions on production during business hours without override
deny[msg] {
    input.environment == "production"
    is_business_hour(input.timestamp)
    input.action.risk_level in ["high", "critical"]
    not has_override(input.action)
    msg := sprintf("High-risk actions not allowed during business hours: %s", [input.action.title])
}

# Deny destructive actions on critical resources
deny[msg] {
    forbidden_action(input.action)
    msg := sprintf("Action forbidden by policy: %s", [input.action.command])
}

is_read_only_action(params) {
    params.action in ["get", "describe", "logs", "top", "list"]
}

forbidden_action(action) {
    action.parsed_params.action == "delete"
    action.parsed_params.resource_type == "namespace"
}

is_business_hour(timestamp) {
    hour := time.hour(timestamp)
    hour >= 9
    hour <= 17
    day := time.weekday(timestamp)
    day >= 1
    day <= 5
}

has_override(action) {
    action.context.override_reason
}
```

### 3.3 OPA Client Integration

```python
# backend/app/governance/opa_client.py

import httpx
from typing import Any, Optional

class OPAClient:
    """Client for OPA policy evaluation."""

    def __init__(self, opa_url: str = "http://localhost:8181"):
        self.opa_url = opa_url
        self.client = httpx.AsyncClient(timeout=5.0)

    async def evaluate_action(
        self,
        action: Action,
        project: str,
        user: Optional[str] = None,
    ) -> PolicyDecision:
        """Evaluate an action against OPA policies."""
        input_data = {
            "action": action.model_dump(),
            "project": project,
            "user": user,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": self._get_environment(project),
        }

        try:
            response = await self.client.post(
                f"{self.opa_url}/v1/data/devops/actions",
                json={"input": input_data},
            )
            result = response.json()

            return PolicyDecision(
                allowed=result.get("allow", False),
                reasons=result.get("reasons", []),
                denied=result.get("deny", []),
            )
        except Exception as e:
            logger.error(f"OPA evaluation failed: {e}")
            return PolicyDecision(
                allowed=False,
                reasons=["Policy evaluation unavailable"],
            )

    def _get_environment(self, project: str) -> str:
        """Get environment for project."""
        registry = get_registry()
        config = registry.get_project(project)
        return config.tags.get("environment", "production") if config else "production"
```

### 3.4 Integration with Action Engine

```python
# Updated validator with OPA

class PolicyAwareCommandValidator(CommandValidator):
    """Command validator with OPA policy integration."""

    def __init__(self):
        super().__init__()
        self.opa_client = OPAClient(settings.OPA_URL)

    async def validate(
        self,
        command: str,
        project: str,
        user: Optional[str] = None,
    ) -> ValidationResult:
        """Validate command against RBAC and OPA policies."""
        # First, do RBAC validation
        rbac_result = await super().validate(command, project, user)

        if not rbac_result.allowed:
            return rbac_result

        # Parse action
        params = self.parser.parse(command)
        action = Action(
            id="temp",
            command=command,
            parsed_params=params,
            project=project,
        )

        # Check OPA policies
        policy_decision = await self.opa_client.evaluate_action(
            action=action,
            project=project,
            user=user,
        )

        if not policy_decision.allowed:
            return ValidationResult(
                is_valid=True,
                allowed=False,
                reason=f"Policy violation: {', '.join(policy_decision.denied)}",
                risk_level=RiskLevel.CRITICAL,
            )

        # Return RBAC result with policy reasons
        return ValidationResult(
            is_valid=rbac_result.is_valid,
            allowed=True,
            requires_approval=rbac_result.requires_approval,
            reason=rbac_result.reason,
            warnings=policy_decision.reasons,
        )
```

---

## 4. Enhanced Audit Logging

### 4.1 Structured Audit Events

```python
# Enhanced audit events for Phase 3

class AuditEventType(str, Enum):
    """Extended audit event types."""
    # Phase 2 events
    ACTION_CREATED = "action_created"
    ACTION_APPROVED = "action_approved"
    ACTION_REJECTED = "action_rejected"
    ACTION_EXECUTED = "action_executed"
    ACTION_FAILED = "action_failed"

    # Phase 3 new events
    SKILL_EXECUTED = "skill_executed"
    SKILL_FAILED = "skill_failed"
    POLICY_CHECK = "policy_check"
    POLICY_DENIED = "policy_denied"
    PERMISSION_DENIED = "permission_denied"
    RBAC_CHECK = "rbac_check"
```

### 4.2 Compliance Export

```python
# backend/app/audit/exporter.py

class AuditExporter:
    """Export audit logs for compliance reporting."""

    async def export_to_csv(
        self,
        query: AuditLogQuery,
        output_path: str,
    ) -> str:
        """Export audit logs to CSV for compliance reporting."""

    async def export_for_sox(
        self,
        quarter: str,
        year: int,
    ) -> dict:
        """Generate SOX compliance report."""
```

---

## API Endpoints

### Skill Management

#### List Skills
**GET** `/api/v1/skills`

```json
{
  "skills": [
    {
      "id": "finops_cost_analyzer",
      "name": "Cloud Cost Analyzer",
      "type": "finops",
      "version": "1.0.0",
      "enabled": true,
      "projects": ["meinvoice"]
    }
  ]
}
```

#### Execute Skill Analysis
**POST** `/api/v1/skills/{skill_id}/analyze`

```json
{
  "project": "meinvoice",
  "time_range": "7d",
  "parameters": {
    "threshold": 20
  }
}
```

#### Get Skill Recommendations
**GET** `/api/v1/skills/{skill_id}/recommendations/{analysis_id}`

### RBAC Management

#### Check Permission
**POST** `/api/v1/governance/permissions/check`

```json
{
  "project": "meinvoice",
  "action": "kubectl delete pod",
  "permission": "execute_safe"
}
```

#### Get Service Account Config
**GET** `/api/v1/governance/service-account/{project}`

### Policy Management

#### Validate Against Policies
**POST** `/api/v1/governance/policies/validate`

```json
{
  "action": {
    "command": "kubectl delete pod xxx",
    "project": "meinvoice"
  }
}
```

#### Get Active Policies
**GET** `/api/v1/governance/policies`

---

## Frontend Components

### SkillsPage

```typescript
// frontend/src/pages/SkillsPage.tsx

export function SkillsPage() {
  return (
    <div>
      <h1>Skills Library</h1>
      <SkillList />
      <SkillExecutionPanel />
    </div>
  );
}
```

### GovernanceDashboard

```typescript
// frontend/src/pages/GovernanceDashboard.tsx

export function GovernanceDashboard() {
  return (
    <div>
      <h1>Governance Dashboard</h1>
      <RBACMatrix />
      <PolicyStatus />
      <ComplianceReport />
    </div>
  );
}
```

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPA_URL` | OPA server URL | `http://localhost:8181` |
| `SKILLS_ENABLED` | Enable skill system | `true` |
| `SKILLS_CONFIG_PATH` | Skills configuration directory | `config/skills` |
| `RBAC_ENABLED` | Enable RBAC for AI | `true` |
| `AI_SA_CONFIG_PATH` | Service account configs | `config/ai_service_accounts.yaml` |

---

## Migration Path

### Week 1-2: Skill Library Foundation
- [ ] Implement `BaseSkill` interface
- [ ] Create `SkillRegistry`
- [ ] Implement FinOps Cost Analyzer skill
- [ ] Add skills API endpoints

### Week 3-4: RBAC for AI
- [ ] Implement `AIPermissionChecker`
- [ ] Create service account configurations
- [ ] Add environment-aware command execution
- [ ] Implement permission checking in Action Engine

### Week 5-6: Policy as Code
- [ ] Deploy OPA server
- [ ] Write Rego policies for common scenarios
- [ ] Implement `OPAClient`
- [ ] Integrate OPA validation in Action Engine
- [ ] Add policy management UI

### Week 7-8: Testing & Documentation
- [ ] Integration tests for skills
- [ ] RBAC permission matrix tests
- [ ] OPA policy validation tests
- [ ] Update documentation

---

## Documentation Updates

- [ ] `docs/skills-library.md` - Skill development guide
- [ ] `docs/governance/rbac.md` - RBAC configuration
- [ ] `docs/governance/opa-policies.md` - Policy writing guide
- [ ] Update `CLAUDE.md` with Phase 3 architecture
