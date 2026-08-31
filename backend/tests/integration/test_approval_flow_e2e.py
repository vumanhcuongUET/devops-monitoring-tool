"""Phase 11 Sprint 4: end-to-end approval flow.

Chain under test:
    alert fires -> autonomous remediation (dry-run) -> action created (PENDING)
    -> signed Slack approval webhook -> execute -> EXECUTED

Only the process boundary is mocked (shell execution, audit/feedback sinks);
parser, validator, RBAC, rate limiter, approval tracker and the Slack
signature verification all run for real.
"""

import hashlib
import hmac
import json
import time
import urllib.parse
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from app.actions.autonomous_executor import get_autonomous_executor
from app.actions.engine import get_action_engine
from app.settings import settings
from app.models.actions import (
    ActionStatus,
    CreateActionRequest,
    ExecuteActionRequest,
)
from app.models.alerts import AlertEvent, AlertRule
from app.models.triage_card import Recommendation, SeverityLevel
from app.models.registry import (
    ClusterConfig,
    NamespaceMapping,
    OwnerContact,
    ProjectConfig,
    RbacConstraints,
    RegistryConfig,
)

SIGNING_SECRET = "e2e-test-signing-secret"


def _test_registry() -> RegistryConfig:
    rbac = RbacConstraints(
        allowed_actions=["kubectl_get", "kubectl_describe", "kubectl_logs"],
        requires_approval=["kubectl_delete", "kubectl_scale", "kubectl_rollout_restart"],
        forbidden_actions=["kubectl_delete_namespace", "kubectl_delete_pvc"],
    )
    project = ProjectConfig(
        name="meinvoice",
        cluster=ClusterConfig(name="test-cluster", context="test-context", platform="kubernetes"),
        namespaces=NamespaceMapping(app="meinvoice", database="meinvoice-db"),
        owners=[OwnerContact(user="team-devops", email="team-devops@example.com", slack="#team-devops")],
        # Alert rule targets environment=development; without this tag the
        # engine derives "production" where RBAC grants no `approve` permission
        # (Phase 12 S6) and the flow can never reach EXECUTED.
        tags={"environment": "development"},
    )
    registry = RegistryConfig()
    registry.projects = [project]
    registry.global_constraints = None
    return registry


def _slack_signature(body: str, timestamp: str) -> str:
    sig_base = f"v0:{timestamp}:{body}"
    digest = hmac.new(SIGNING_SECRET.encode(), sig_base.encode(), hashlib.sha256).hexdigest()
    return f"v0={digest}"


@pytest.mark.integration
class TestApprovalFlowE2E:
    async def test_alert_to_executed_full_flow(self):
        # -- Shared engine with a test registry -----------------------------
        engine = get_action_engine()
        original_registry = engine.registry
        engine.registry = _test_registry()

        # -- Step 1: alert fires -> autonomous remediation dry-run ---------
        rule = AlertRule(
            id="rule-e2e",
            name="crashloop-backoff",
            source="prometheus",
            metric="kube_pod_container_status_restarts_total",
            condition="gt",
            threshold=10,
            severity="critical",
            labels={"environment": "development"},
            autonomous_action={
                "enabled": True,
                "action_type": "restart_deployment",
                "dry_run": True,
            },
        )
        event = AlertEvent(
            id=f"evt-{uuid.uuid4().hex[:8]}",
            rule_id=rule.id,
            rule_name=rule.name,
            severity="critical",
            status="firing",
            value=42.0,
            threshold=rule.threshold,
            message="CrashLoopBackOff detected",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        mock_result = MagicMock(success=True, exit_code=0, stdout="[DRY-RUN] would restart deployment api")
        with (
            patch("app.actions.autonomous_executor.RemediationActionFactory") as mock_factory,
            # The executor builds its own AuditLogger() and calls log_event() —
            # patch the class or every run writes real entries to data/audit/ (review A2).
            patch("app.actions.autonomous_executor.AuditLogger"),
        ):
            mock_action = MagicMock()
            mock_action.execute = AsyncMock(return_value=mock_result)
            mock_factory.create.return_value = mock_action

            executor = get_autonomous_executor()
            remediation = await executor.execute_autonomous_action(
                alert_rule=rule,
                alert_event=event,
                environment="development",
                dry_run=True,
            )
        assert remediation.success is True
        assert "[DRY-RUN]" in (remediation.stdout or "")

        # -- Step 2: action created from recommendation (PENDING) ----------
        try:
            recommendation = Recommendation(
                priority=1,
                action="Scale deployment api to 3 replicas",
                command="kubectl scale deployment api --replicas=3 -n meinvoice",
                reason="CrashLoopBackOff after bad rollout",
                risk=SeverityLevel.HIGH,
            )
            action = await engine.create_action_from_recommendation(
                request=CreateActionRequest(
                    triage_card_id="tc-e2e",
                    recommendation_id="rec-e2e",
                    project="meinvoice",
                ),
                recommendation=recommendation,
            )
            assert action.status == ActionStatus.PENDING, (
                f"scale requires approval, got {action.status}"
            )
            action_id = action.id

            # -- Step 3: signed Slack approval webhook ----------------------
            payload = json.dumps({
                "actions": [{"action_id": "approve_action", "value": f"approve_action:{action_id}"}],
                "user": {"id": "U123", "name": "alice"},
            })
            body = urllib.parse.urlencode({"payload": payload})
            timestamp = str(int(time.time()))
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": _slack_signature(body, timestamp),
            }

            webhook_app = FastAPI()
            from app.approvals.webhook import router as webhook_router

            webhook_app.include_router(webhook_router)

            original_secret = settings.SLACK_SIGNING_SECRET
            settings.SLACK_SIGNING_SECRET = SIGNING_SECRET
            # Phase B approval gate: the chat identity maps to a platform user.
            original_gate = settings.CHATOPS_APPROVALS_ENABLED
            original_map = settings.SLACK_APPROVER_MAP
            settings.CHATOPS_APPROVALS_ENABLED = True
            settings.SLACK_APPROVER_MAP = {"U123": "alice"}
            with patch("app.users.get_role", return_value="admin"):
                try:
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=webhook_app), base_url="http://test"
                    ) as client:
                        resp = await client.post("/approvals/webhook/slack", content=body, headers=headers)
                finally:
                    settings.SLACK_SIGNING_SECRET = original_secret
                    settings.CHATOPS_APPROVALS_ENABLED = original_gate
                    settings.SLACK_APPROVER_MAP = original_map

            assert resp.status_code == 200, resp.text
            approved_state = await engine.approval_tracker.get(action_id)
            assert approved_state["status"] == ActionStatus.APPROVED

            # -- Step 4: execute the approved action ------------------------
            result = MagicMock(success=True, exit_code=0, stdout="deployment.apps/api scaled", stderr="")
            with patch.object(
                engine.env_aware_executor, "execute", AsyncMock(return_value=result)
            ):
                executed = await engine.execute_action(
                    action_id,
                    ExecuteActionRequest(executed_by="alice"),
                )
            assert executed.status == ActionStatus.EXECUTED

            # -- Step 5: tampered signature rejected post-hoc ----------------
            bad_headers = dict(headers)
            bad_headers["X-Slack-Signature"] = "v0=" + "0" * 64
            settings.SLACK_SIGNING_SECRET = SIGNING_SECRET
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=webhook_app), base_url="http://test"
                ) as client:
                    bad_resp = await client.post(
                        "/approvals/webhook/slack", content=body, headers=bad_headers
                    )
            finally:
                settings.SLACK_SIGNING_SECRET = original_secret
            assert bad_resp.status_code == 401
        finally:
            engine.registry = original_registry

    async def test_approve_permission_denied_returns_200(self):
        """S6: denied approval is a normal outcome — webhook must answer 200
        (ephemeral denial), not 500, so Slack does not retry the interaction."""
        engine = get_action_engine()
        original_registry = engine.registry
        # The read-only production matrix grants `approve` to nobody (plain
        # production must keep APPROVE reachable — the old empty-tags deny
        # here relied on the paradox the Phase 12 manual smoke fixed: prod
        # approvals were impossible for anyone, admin included).
        engine.registry = _test_registry()
        engine.registry.projects[0].tags = {"environment": "production-read-only"}

        original_secret = settings.SLACK_SIGNING_SECRET
        settings.SLACK_SIGNING_SECRET = SIGNING_SECRET
        try:
            recommendation = Recommendation(
                priority=1,
                action="Scale deployment api to 3 replicas",
                command="kubectl scale deployment api --replicas=3 -n meinvoice",
                reason="CrashLoopBackOff after bad rollout",
                risk=SeverityLevel.HIGH,
            )
            action = await engine.create_action_from_recommendation(
                request=CreateActionRequest(
                    triage_card_id="tc-denied",
                    recommendation_id="rec-denied",
                    project="meinvoice",
                ),
                recommendation=recommendation,
            )
            assert action.status == ActionStatus.PENDING
            action_id = action.id

            payload = json.dumps({
                "actions": [{"action_id": "approve_action", "value": f"approve_action:{action_id}"}],
                "user": {"id": "U123", "name": "alice"},
            })
            body = urllib.parse.urlencode({"payload": payload})
            timestamp = str(int(time.time()))
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Slack-Request-Timestamp": timestamp,
                "X-Slack-Signature": _slack_signature(body, timestamp),
            }

            webhook_app = FastAPI()
            from app.approvals.webhook import router as webhook_router
            webhook_app.include_router(webhook_router)

            # Gate on so the request reaches the ENGINE's RBAC denial (the
            # thing under test) rather than the chat-membership gate.
            original_gate = settings.CHATOPS_APPROVALS_ENABLED
            original_map = settings.SLACK_APPROVER_MAP
            try:
                settings.CHATOPS_APPROVALS_ENABLED = True
                settings.SLACK_APPROVER_MAP = {"U123": "alice"}
                with patch("app.users.get_role", return_value="admin"):
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=webhook_app), base_url="http://test"
                    ) as client:
                        resp = await client.post("/approvals/webhook/slack", content=body, headers=headers)
            finally:
                settings.CHATOPS_APPROVALS_ENABLED = original_gate
                settings.SLACK_APPROVER_MAP = original_map
            assert resp.status_code == 200, resp.text
            assert "Refused" in resp.text or "not permitted" in resp.text or "denied" in resp.text.lower() or "🚫" in resp.text

            denied_state = await engine.approval_tracker.get(action_id)
            assert denied_state["status"] == ActionStatus.PENDING
        finally:
            settings.SLACK_SIGNING_SECRET = original_secret
            engine.registry = original_registry
