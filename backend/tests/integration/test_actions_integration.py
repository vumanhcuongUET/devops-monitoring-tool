"""Integration tests for Actions system.

These tests verify component interactions and end-to-end flows.
"""

import asyncio
import uuid
from unittest.mock import patch

import pytest

from app.actions.executor import CommandExecutor
from app.actions.parser import CommandParser
from app.actions.validator import CommandValidator
from app.approvals.store import ApprovalStateTracker
from app.audit.logger import AuditLogger
from app.models.actions import (
    ActionStatus,
    CommandType,
    RiskLevel,
)
from app.models.audit import AuditLogQuery
from app.models.registry import (
    ClusterConfig,
    NamespaceMapping,
    OwnerContact,
    ProjectConfig,
    RbacConstraints,
    RegistryConfig,
)


@pytest.fixture
def test_registry():
    """Create test registry with sample project config."""
    rbac = RbacConstraints(
        allowed_actions=["kubectl_get", "kubectl_describe", "kubectl_logs"],
        requires_approval=["kubectl_delete", "kubectl_scale", "kubectl_rollout_restart"],
        forbidden_actions=["kubectl_delete_namespace", "kubectl_delete_pvc"],
    )

    cluster = ClusterConfig(
        name="test-cluster",
        context="test-context",
        platform="kubernetes",
    )
    namespaces = NamespaceMapping(
        app="meinvoice",
        database="meinvoice-db",
    )

    project = ProjectConfig(
        name="meinvoice",
        cluster=cluster,
        namespaces=namespaces,
        rbac=rbac,
        owners=[OwnerContact(user="team-devops", email="team-devops@example.com", slack="#team-devops")],
    )

    registry = RegistryConfig()
    registry.projects = [project]
    registry.global_constraints = None

    return registry


@pytest.fixture
def unique_action_id():
    """Generate unique action ID for each test."""
    return f"act-{uuid.uuid4().hex[:8]}"


@pytest.mark.integration
class TestParserValidatorIntegration:
    """Test integration between parser and validator."""

    async def test_parse_then_validate_safe_command(self, test_registry):
        """Test parsing and then validating a safe command."""
        parser = CommandParser()
        validator = CommandValidator()

        # Set up validator with test registry
        validator.registry = test_registry
        validator.parser = parser

        # Parse the command
        command = "kubectl get pods -n meinvoice"
        params = parser.parse(command)

        assert params.command_type == CommandType.KUBECTL
        assert params.resource_type == "pod"  # Parser normalizes to singular form
        assert params.action == "get"

        # Validate the parsed command
        result = validator.validate(
            command=command,
            project="meinvoice",
        )

        assert result.is_valid is True
        assert result.risk_level == RiskLevel.LOW  # Safe commands are LOW risk

    async def test_parse_then_validate_risky_command(self, test_registry):
        """Test parsing and then validating a risky command."""
        parser = CommandParser()
        validator = CommandValidator()

        # Set up validator with test registry
        validator.registry = test_registry
        validator.parser = parser

        # Parse the risky command
        command = "kubectl delete pod test-pod -n meinvoice"
        params = parser.parse(command)

        assert params.command_type == CommandType.KUBECTL
        assert params.action == "delete"

        # Validate - should require approval
        result = validator.validate(
            command=command,
            project="meinvoice",
        )

        # Delete operations are considered risky
        assert result.requires_approval is True
        assert result.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]


@pytest.mark.integration
class TestApprovalTrackerPersistence:
    """Test approval state persistence integration."""

    async def test_action_persisted_and_retrieved(self, unique_action_id):
        """Test that action can be persisted and retrieved from tracker."""
        tracker = ApprovalStateTracker()

        # Track the action using set_status
        await tracker.set_status(
            action_id=unique_action_id,
            status=ActionStatus.PENDING,
        )

        # Retrieve it
        retrieved = await tracker.get(unique_action_id)

        assert retrieved is not None
        assert retrieved["status"] == ActionStatus.PENDING

        # Clean up
        await tracker.delete(unique_action_id)

    async def test_action_status_updates_persist(self, unique_action_id):
        """Test that status updates are persisted."""
        tracker = ApprovalStateTracker()

        # Track as pending
        await tracker.set_status(
            action_id=unique_action_id,
            status=ActionStatus.PENDING,
        )

        # Update to approved
        await tracker.set_status(
            action_id=unique_action_id,
            status=ActionStatus.APPROVED,
            user="admin",
        )

        # Retrieve and verify
        retrieved = await tracker.get(unique_action_id)
        assert retrieved["status"] == ActionStatus.APPROVED

        # Clean up
        await tracker.delete(unique_action_id)


class FakeStream:
    """Pipe reader that yields the given bytes then EOF (the executor reads
    streams directly since the Phase 15 capture cap — communicate() mocks
    here used to spin forever because an AsyncMock read never returns
    EOF)."""

    def __init__(self, data: bytes = b""):
        self._data = data

    async def read(self, n: int = -1) -> bytes:
        size = len(self._data) if n < 0 else min(n, len(self._data))
        chunk, self._data = self._data[:size], self._data[size:]
        return chunk


class HangingStream:
    """Stream whose read never completes — drives the timeout path."""

    async def read(self, n: int = -1) -> bytes:
        await asyncio.sleep(3600)
        return b""


class FakeProcess:
    """Process with real stream objects for the executor's capped reads."""

    def __init__(self, stdout: bytes = b"", stderr: bytes = b"",
                 returncode: int = 0, hang: bool = False):
        self.stdout = HangingStream() if hang else FakeStream(stdout)
        self.stderr = HangingStream() if hang else FakeStream(stderr)
        self.returncode = returncode
        self.killed = False

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


@pytest.mark.integration
class TestExecutorWithErrorHandling:
    """Test executor error handling integration."""

    @pytest.mark.asyncio
    async def test_executor_timeout_handling(self):
        """The executor kills a hung command and reports the timeout."""
        executor = CommandExecutor()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_subprocess.return_value = FakeProcess(hang=True)

            result = await executor.execute("kubectl get pods", timeout_seconds=1)

        assert result.success is False
        assert "timed out" in (result.error_message or "")

    @pytest.mark.asyncio
    async def test_executor_command_failure_handling(self):
        """Test that executor handles command failures."""
        executor = CommandExecutor()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_subprocess.return_value = FakeProcess(
                stderr=b"Error: pods not found", returncode=1
            )

            result = await executor.execute("kubectl get pods")

        assert result.success is False
        assert result.exit_code == 1
        assert "not found" in result.stderr

    @pytest.mark.asyncio
    async def test_executor_success_case(self):
        """Test successful command execution."""
        executor = CommandExecutor()

        with patch("asyncio.create_subprocess_exec") as mock_subprocess:
            mock_subprocess.return_value = FakeProcess(
                stdout=b"pod/test-pod ready", returncode=0
            )

            result = await executor.execute("kubectl get pods")

        assert result.success is True
        assert result.exit_code == 0
        assert "ready" in result.stdout


@pytest.mark.integration
class TestConcurrentOperations:
    """Test concurrent operation handling."""

    async def test_concurrent_action_status_updates(self):
        """Test that multiple status updates work correctly."""
        tracker = ApprovalStateTracker()

        # Create multiple unique action IDs
        action_ids = [f"act-{uuid.uuid4().hex[:8]}" for _ in range(5)]

        # Set status for all (set_status is synchronous)
        for action_id in action_ids:
            await tracker.set_status(action_id, ActionStatus.PENDING)

        # Verify all are persisted
        for action_id in action_ids:
            retrieved = await tracker.get(action_id)
            assert retrieved is not None
            assert retrieved["status"] == ActionStatus.PENDING

        # Clean up
        for action_id in action_ids:
            await tracker.delete(action_id)


@pytest.mark.integration
class TestAuditLogging:
    """Test audit logging with unique action IDs."""

    async def test_audit_logging_basic_flow(self, unique_action_id):
        """Test basic audit logging flow with unique ID."""
        logger = AuditLogger()

        # Log action creation
        logger.log_action_created(
            action_id=unique_action_id,
            triage_card_id="tc-001",
            project="meinvoice",
            command="kubectl get pods",
        )

        # Query for our specific action
        query = AuditLogQuery(action_id=unique_action_id)
        result = logger.query(query)

        # Should find our action
        assert result.total >= 1
        action_entries = [e for e in result.entries if e.action_id == unique_action_id]
        assert len(action_entries) >= 1

        created_entries = [e for e in action_entries if e.event_type.value == "action_created"]
        assert len(created_entries) >= 1
