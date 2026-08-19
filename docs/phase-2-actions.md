# Phase 2: Human-in-the-loop Actions System

## Tổng quan

**Phase 2** mở rộng nền tảng từ **READ-ONLY** (Phase 1) sang **ACTION PROPOSAL** với quy trình phê duyệt của con người (Human-in-the-loop). Điều này cho phép AI đề xuất và thực thi các hành động khắc phục sự cố một cách an toàn và có kiểm soát.

### Cách hoạt động

```
┌─────────────────────────────────────────────────────────────────────┐
│                     1. Triage Card Generated                         │
│                 (AI phân tích sự cố - Phase 1)                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              2. Recommendations to Actions                           │
│  • AI đề xuất các hành động (kubectl, helm, argocd commands)        │
│  • Mỗi recommendation được convert thành một Action                 │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              3. Validation & Risk Assessment                        │
│  • Parser phân tích command type (kubectl/helm/argocd)                │
│  • Validator kiểm tra RBAC policies của dự án                       │
│  • Đánh giá risk level (SAFE, LOW, MEDIUM, HIGH, CRITICAL)          │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              4. Approval Workflow                                    │
│  • Actions cần approval: PENDING → Slack/Teams notification         │
│  • Actions read-only: PENDING → APPROVED (auto)                      │
│  • Người dùng bấm Approve/Reject qua Slack buttons                  │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              5. Execution & Audit                                   │
│  • Executor chạy command với dry_run option                         │
│  • Audit Logger ghi lại toàn bộ Chain of Thought                   │
│  • WebSocket broadcast status updates                               │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              6. Result & Feedback                                   │
│  • Status: EXECUTED hoặc FAILED                                     │
│  • Execution result: stdout, stderr, exit code, duration           │
│  • Lưu vào Approval History cho feedback loop                       │
└─────────────────────────────────────────────────────────────────────┘
```

## Architecture

### Components

| Component | Description |
|-----------|-------------|
| **Actions Engine** | Orchestrate action lifecycle: create → validate → approve → execute |
| **Command Parser** | Parse kubectl/helm/argocd commands into structured params |
| **Command Validator** | Validate against project RBAC policies |
| **Command Executor** | Execute commands with safety constraints |
| **Approval Workflow** | Track approval state, send Slack notifications |
| **Audit Logger** | Log all actions for compliance and debugging |
| **Context Registry** | Store project-specific configs (clusters, namespaces, owners) |

### Data Flow

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│ Frontend     │─────>│ Backend API  │─────>│ Action       │
│ (ActionsPage)│      │ /api/v1/...  │      │ Engine       │
└──────────────┘      └──────────────┘      └──────┬───────┘
                                                     │
                      ┌──────────────────────────────┼────────────────┐
                      │                              │                │
                      ▼                              ▼                ▼
              ┌──────────────┐            ┌──────────────┐  ┌──────────────┐
              │ Approval     │            │ Validator    │  │ Audit Logger  │
              │ Store        │            │ (RBAC check) │  │               │
              └──────┬───────┘            └──────────────┘  └──────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Slack/Teams  │
              │ Webhook      │
              └──────────────┘
```

## API Endpoints

### Actions Management

#### Create Action

**POST** `/api/v1/actions`

```json
{
  "triage_card_id": "tc-001",
  "recommendation_id": "rec-001",
  "project": "meinvoice"
}
```

**Response:**
```json
{
  "success": true,
  "action": {
    "id": "act-123",
    "triage_card_id": "tc-001",
    "recommendation_id": "rec-001",
    "command_type": "kubectl",
    "command": "kubectl get pods -n meinvoice",
    "parsed_params": {
      "command_type": "kubectl",
      "resource_type": "pod",
      "namespace": "meinvoice",
      "action": "get"
    },
    "project": "meinvoice",
    "title": "Check pod status",
    "description": "Verify pod health",
    "risk_level": "safe",
    "estimated_impact": "No impact (read-only)",
    "status": "approved",
    "created_at": "2026-08-18T10:00:00Z"
  }
}
```

#### List Actions

**GET** `/api/v1/actions?project=meinvoice&status=pending&limit=50`

**Response:**
```json
{
  "total": 15,
  "pending": 5,
  "approved": 3,
  "rejected": 2,
  "executed": 4,
  "failed": 1,
  "actions": [...]
}
```

#### Get Action Details

**GET** `/api/v1/actions/{action_id}`

#### Approve Action

**POST** `/api/v1/actions/{action_id}/approve`

```json
{
  "approved_by": "john.doe",
  "comment": "Approved after review - safe operation"
}
```

#### Reject Action

**POST** `/api/v1/actions/{action_id}/reject`

```json
{
  "rejected_by": "john.doe",
  "reason": "Too risky during business hours"
}
```

#### Execute Action

**POST** `/api/v1/actions/{action_id}/execute`

```json
{
  "executed_by": "john.doe",
  "dry_run": false
}
```

#### Bulk Create Actions

**POST** `/api/v1/actions/bulk?triage_card_id=tc-001&project=meinvoice`

Tạo tất cả actions từ một Triage Card cùng lúc.

#### Action Statistics

**GET** `/api/v1/actions/stats/summary`

## Project Configuration (RBAC)

Mỗi dự án có một file config YAML trong `projects/` directory:

 Ví dụ: `projects/meinvoice.yaml`

```yaml
name: meinvoice
display_name: "MeInvoice Service"

cluster:
  name: production-cluster
  context: arn:aws:eks:ap-southeast-1:123456789:cluster/production
  region: ap-southeast-1
  platform: kubernetes

namespaces:
  app: meinvoice
  database: meinvoice-db
  monitoring: monitoring

owners:
  - user: john.doe
    email: john.doe@example.com
    slack: U12345678

rbac:
  # Actions được phép chạy mà không cần approval
  allowed_actions:
    - kubectl_get
    - kubectl_describe
    - kubectl_logs
    - kubectl_top

  # Actions cần approval
  requires_approval:
    - kubectl_delete
    - kubectl_scale
    - kubectl_restart
    - kubectl_rollout_restart
    - helm_upgrade
    - argocd_sync

  # Actions bị cấm tuyệt đối
  forbidden_actions:
    - kubectl_delete_namespace
    - kubectl_delete_pvc
    - cluster_admin_commands

  # Rate limiting
  max_restarts_per_hour: 5

  # Actions cần comment khi approve
  requires_comment_for:
    - kubectl_delete
    - kubectl_scale
    - helm_upgrade
```

## Risk Levels

| Risk Level | Description | Auto-approve? |
|------------|-------------|---------------|
| **SAFE** | Read-only commands (get, describe, logs) | ✅ Yes |
| **LOW** | Non-destructive changes (rollout restart) | ✅ Yes |
| **MEDIUM** | Changes with minor impact (scale up/down) | ❌ No |
| **HIGH** | Destructive changes (delete resources) | ❌ No |
| **CRITICAL** | Forbidden operations | ❌ Blocked |

## Command Types Supported

### kubectl

```bash
# Get operations (SAFE)
kubectl get pods -n meinvoice
kubectl describe deployment api -n meinvoice
kubectl logs -f pod-123 -n meinvoice

# Restart operations (LOW)
kubectl rollout restart deployment/api -n meinvoice

# Scale operations (MEDIUM)
kubectl scale deployment/api --replicas=5 -n meinvoice

# Delete operations (HIGH)
kubectl delete pod pod-123 -n meinvoice
```

### helm

```bash
# Upgrade (HIGH)
helm upgrade meinvoice ./chart -n meinvoice

# Rollback (HIGH)
helm rollback meinvoice 1 -n meinvoice
```

### argocd

```bash
# Sync application (MEDIUM)
argocd app sync meinvoice

# Rollback (HIGH)
argocd app rollback meinvoice
```

## Slack Integration

### Approval Request Message

Khi một action cần approval, Slack message được gửi với:

```
🟠 Action Approval Required

┌─────────────────────────────────────────┐
│ Action ID:    act-123                   │
│ Project:      meinvoice                 │
│ Risk Level:   HIGH                      │
│ Command:      kubectl delete pod-123    │
└─────────────────────────────────────────┘

Restart deployment api to clear transient issues

Estimated Impact: Brief service interruption

───────────────────────────────────────────

[✅ Approve]  [❌ Reject]  [🔍 View Details]
```

### Status Update Message

Sau khi action được approve/reject/execute:

```
✅ Action act-123 status updated to approved

Performed by john.doe

Result: Success
```

## Audit Logging

Tất cả actions được log với:

- **Action Created**: Khi action được tạo từ recommendation
- **Action Approved**: Khi được approve bởi user
- **Action Rejected**: Khi bị reject với reason
- **Action Executed**: Khi được execute với kết quả
- **Action Failed**: Khi execution thất bại

Log entries include:
- Timestamp
- User who performed action
- Command executed
- Output (stdout/stderr)
- Duration
- Risk level

## Frontend Components

### ActionsPage

Main page để xem và quản lý actions:

- **ActionList**: Table với filter by project, status, risk level
- **ActionCard**: Chi tiết từng action với Approve/Reject/Execute buttons
- **Real-time updates**: WebSocket connection cho live status updates

### Component Structure

```
frontend/src/
├── pages/
│   └── ActionsPage.tsx          # Main actions management page
├── components/
│   ├── actions/
│   │   ├── ActionList.tsx        # Table of actions
│   │   ├── ActionCard.tsx       # Single action detail
│   │   └── ApprovalButtons.tsx  # Approve/Reject/Execute buttons
└── hooks/
    └── useActions.ts            # TanStack Query hooks
```

## Usage Examples

### Python

```python
import httpx

async def create_and_approve_action():
    async with httpx.AsyncClient() as client:
        # 1. Create action
        response = await client.post(
            "http://localhost:8000/api/v1/actions",
            json={
                "triage_card_id": "tc-001",
                "recommendation_id": "rec-001",
                "project": "meinvoice"
            }
        )
        action = response.json()["action"]

        # 2. Approve (if needed)
        if action["status"] == "pending":
            await client.post(
                f"http://localhost:8000/api/v1/actions/{action['id']}/approve",
                json={
                    "approved_by": "john.doe",
                    "comment": "Safe to proceed"
                }
            )

        # 3. Execute
        await client.post(
            f"http://localhost:8000/api/v1/actions/{action['id']}/execute",
            json={
                "executed_by": "john.doe",
                "dry_run": False
            }
        )
```

### cURL

```bash
# Create action
ACTION=$(curl -s -X POST http://localhost:8000/api/v1/actions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "triage_card_id": "tc-001",
    "recommendation_id": "rec-001",
    "project": "meinvoice"
  }' | jq -r '.action.id')

# Approve action
curl -X POST http://localhost:8000/api/v1/actions/$ACTION/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "approved_by": "john.doe",
    "comment": "Approved"
  }'

# Execute action
curl -X POST http://localhost:8000/api/v1/actions/$ACTION/execute \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "executed_by": "john.doe",
    "dry_run": false
  }'
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SLACK_APPROVAL_WEBHOOK_URL` | Slack incoming webhook for approval requests | — |
| `COMMAND_EXECUTION_TIMEOUT` | Max time for command execution (seconds) | 30 |
| `MAX_COMMAND_OUTPUT_LENGTH` | Max output length to store (bytes) | 10000 |
| `DRY_RUN_DEFAULT` | Default dry_run mode | true |

## Best Practices

### 1. Command Writing

**Good:**
```bash
kubectl rollout restart deployment/api -n meinvoice
kubectl get pods -n meinvoice -l app=api
```

**Bad:**
```bash
kubectl delete pod --all -n meinvoice  # Too dangerous
kubectl rollout restart deployment/* -n *  # Too vague
```

### 2. Risk Assessment

- Always check `risk_level` before approving
- High/Critical actions cần review kỹ lưỡng
- Sử dụng `dry_run=true` cho test đầu tiên

### 3. Approval Comments

```json
{
  "approved_by": "john.doe",
  "comment": "Reviewed - safe to proceed during low traffic period"
}
```

Comments quan trọng cho audit trail.

### 4. Rate Limiting

Giới hạn số lượng dangerous actions per hour:
- `max_restarts_per_hour: 5`
- `max_deletes_per_hour: 2`

## Security Features

### 1. SSRF Protection

Webhook URLs được validate để chặn internal IP access.

### 2. Command Validation

Tất cả commands được validate trước khi execute:
- Check against project RBAC
- Verify namespace access
- Forbidden action blocking

### 3. Audit Trail

Tất cả actions được logged với:
- User identity
- Timestamp
- Command executed
- Result

### 4. Least Privilege

Commands execute với:
- Project-scoped kubeconfig
- Namespace-restricted access
- Time-limited tokens

## Troubleshooting

### Action stuck in PENDING

**Cause:** Slack webhook không configured hoặc failed.

**Solution:**
1. Check `SLACK_APPROVAL_WEBHOOK_URL` in `.env`
2. Verify webhook URL is allowed (not blocked by SSRF)
3. Use API to approve manually

### Execution FAILED

**Cause:** Command invalid, resource không tồn tại, hoặc permission denied.

**Solution:**
1. Check `execution_result.stderr` for error details
2. Verify resource exists: `kubectl get <resource>`
3. Check RBAC permissions for service account

### Forbidden Action

**Cause:** Action nằm trong `forbidden_actions` list của project config.

**Solution:**
1. Review project RBAC config
2. Cần owner approval để thay đổi config
3. Consider alternative safer action

## Phase 3 Preview

Phase 3 sẽ thêm:
- **Skill Library**: FinOps, Security, Capacity Planning skills
- **RBAC for AI**: Agent permissions per environment
- **Policy as Code**: OPA integration for policy enforcement

Xem [docs/chien_luoc_tong_the.md](chien_luoc_tong_the.md) để biết thêm.
