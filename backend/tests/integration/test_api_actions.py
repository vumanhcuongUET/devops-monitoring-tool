"""Integration tests for Actions API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.main import app
from app.models.actions import ActionStatus, RiskLevel
from app.config import settings


@pytest.fixture
def client(monkeypatch):
    """Create test client (auth disabled — auth behavior covered in its own tests)."""
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)
    return TestClient(app)


@pytest.fixture
def mock_action_engine():
    """Mock ActionEngine."""
    engine = AsyncMock()
    engine.list_actions = MagicMock()
    engine.get_action = MagicMock()
    return engine


@pytest.fixture
def mock_registry():
    """Mock registry."""
    registry = MagicMock()
    registry.projects = []
    return registry


class TestActionsAPI:
    """Test Actions API endpoints."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self, mock_action_engine, mock_registry):
        """Setup common mocks."""
        app.state.action_engine = mock_action_engine
        app.state.registry = mock_registry

        # Reset mocks before each test
        mock_action_engine.reset_mock()

    def test_create_action_success(self, client, mock_action_engine):
        """Test successful action creation."""
        # Mock engine response
        from app.models.actions import Action, CommandType, CommandParams

        mock_action_engine.create_action_from_recommendation = AsyncMock(
            return_value=Action(
                id="act-123",
                triage_card_id="tc-001",
                recommendation_id="rec-001",
                command_type=CommandType.KUBECTL,
                command="kubectl get pods",
                parsed_params=CommandParams(
                    command_type=CommandType.KUBECTL,
                    action="get",
                ),
                project="meinvoice",
                title="Check pod status",
                description="Verify pod health",
                risk_level=RiskLevel.SAFE,
                status=ActionStatus.APPROVED,
            )
        )

        response = client.post(
            "/api/v1/actions",
            json={
                "triage_card_id": "tc-001",
                "recommendation_id": "rec-001",
                "project": "meinvoice",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["action"]["id"] == "act-123"
        assert data["action"]["status"] == ActionStatus.APPROVED

    def test_create_action_invalid_request(self, client):
        """Test action creation with invalid request."""
        response = client.post(
            "/api/v1/actions",
            json={
                "triage_card_id": "tc-001",
                # Missing recommendation_id and project
            },
        )

        assert response.status_code == 422  # Validation error

    def test_list_actions(self, client, mock_action_engine):
        """Test listing actions."""
        # Mock engine response
        from app.models.actions import ActionListResponse

        mock_action_engine.list_actions.return_value = ActionListResponse(
            total=2,
            pending=1,
            approved=1,
            rejected=0,
            executed=0,
            failed=0,
            actions=[],
        )

        response = client.get("/api/v1/actions")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert data["pending"] == 1

    def test_list_actions_with_filters(self, client, mock_action_engine):
        """Test listing actions with filters."""
        mock_action_engine.list_actions.return_value = MagicMock(
            total=1, pending=1, approved=0, rejected=0, executed=0, failed=0, actions=[]
        )

        response = client.get("/api/v1/actions?project=meinvoice&status=pending")

        assert response.status_code == 200
        mock_action_engine.list_actions.assert_called_once()

    def test_get_action_success(self, client, mock_action_engine):
        """Test getting action by ID."""
        mock_action_engine.get_action.return_value = {
            "id": "act-123",
            "status": "approved",
            "command": "kubectl get pods",
        }

        response = client.get("/api/v1/actions/act-123")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action"]["id"] == "act-123"

    def test_get_action_not_found(self, client, mock_action_engine):
        """Test getting non-existent action."""
        mock_action_engine.get_action.return_value = None

        response = client.get("/api/v1/actions/nonexistent")

        assert response.status_code == 404

    def test_approve_action_success(self, client, mock_action_engine):
        """Test approving action."""
        from app.models.actions import Action, ActionStatus

        mock_action_engine.approve_action = AsyncMock(
            return_value=Action(
                id="act-123",
                status=ActionStatus.APPROVED,
                approved_by="john.doe",
            )
        )

        response = client.post(
            "/api/v1/actions/act-123/approve",
            json={
                "approved_by": "john.doe",
                "comment": "Approved after review",
            },
        )

        assert response.status_code in [200, 202]
        data = response.json()
        assert data["success"] is True

    def test_approve_action_invalid_request(self, client):
        """Test approving with invalid request."""
        response = client.post(
            "/api/v1/actions/act-123/approve",
            json={
                # Missing approved_by
                "comment": "Approved",
            },
        )

        assert response.status_code == 422

    def test_reject_action_success(self, client, mock_action_engine):
        """Test rejecting action."""
        from app.models.actions import Action, ActionStatus

        mock_action_engine.reject_action = AsyncMock(
            return_value=Action(
                id="act-123",
                status=ActionStatus.REJECTED,
                rejected_by="john.doe",
            )
        )

        response = client.post(
            "/api/v1/actions/act-123/reject",
            json={
                "rejected_by": "john.doe",
                "reason": "Too risky",
            },
        )

        assert response.status_code in [200, 202]
        data = response.json()
        assert data["success"] is True

    def test_execute_action_success(self, client, mock_action_engine):
        """Test executing action."""
        from app.models.actions import Action, ActionStatus, ExecutionResult

        mock_action_engine.execute_action = AsyncMock(
            return_value=Action(
                id="act-123",
                status=ActionStatus.EXECUTED,
                executed_by="john.doe",
                execution_result=ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout="Command successful",
                    stderr="",
                ),
            )
        )

        response = client.post(
            "/api/v1/actions/act-123/execute",
            json={
                "executed_by": "john.doe",
                "dry_run": False,
            },
        )

        assert response.status_code in [200, 202]
        data = response.json()
        assert data["success"] is True

    def test_execute_action_dry_run(self, client, mock_action_engine):
        """Test executing action with dry run."""
        from app.models.actions import Action, ActionStatus, ExecutionResult

        mock_action_engine.execute_action = AsyncMock(
            return_value=Action(
                id="act-123",
                status=ActionStatus.EXECUTED,
                executed_by="john.doe",
                execution_result=ExecutionResult(
                    success=True,
                    exit_code=0,
                    stdout="[DRY RUN] Command validated",
                    stderr="",
                ),
            )
        )

        response = client.post(
            "/api/v1/actions/act-123/execute",
            json={
                "executed_by": "john.doe",
                "dry_run": True,
            },
        )

        assert response.status_code in [200, 202]

    def test_bulk_create_actions(self, client, mock_action_engine):
        """Test bulk action creation."""
        from app.models.actions import Action, CommandType, ActionStatus

        mock_action_engine.create_action_from_recommendation = AsyncMock(
            return_value=Action(
                id="act-123",
                status=ActionStatus.PENDING,
                command_type=CommandType.KUBECTL,
                command="kubectl get pods",
                project="meinvoice",
                title="Test",
                description="Test action",
                risk_level=RiskLevel.SAFE,
            )
        )

        response = client.post(
            "/api/v1/actions/bulk?triage_card_id=tc-001&project=meinvoice",
        )

        assert response.status_code in [200, 201]
        data = response.json()
        assert "total_created" in data

    def test_get_action_stats(self, client, mock_action_engine):
        """Test getting action statistics."""
        mock_action_engine.list_actions.return_value = MagicMock(
            total=10, pending=3, approved=5, rejected=1, executed=1, failed=0, actions=[]
        )

        response = client.get("/api/v1/actions/stats/summary")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "pending" in data
        assert data["total"] == 10


class TestActionsAPIAuthentication:
    """Test Actions API authentication."""

    def test_actions_protected_without_auth(self, client, monkeypatch):
        """Test that actions are protected without authentication."""
        # Enable auth
        from app.config import settings
        original_auth = settings.AUTH_ENABLED
        monkeypatch.setattr(settings, "AUTH_ENABLED", True)

        # Clear API keys to force auth failure
        monkeypatch.setattr(settings, "API_KEYS", [])

        response = client.get("/api/v1/actions")

        # Should be unauthorized
        assert response.status_code == 401

        # Restore
        monkeypatch.setattr(settings, "AUTH_ENABLED", original_auth)

    def test_actions_with_valid_api_key(self, client, monkeypatch):
        """Test actions with valid API key."""
        from app.config import settings

        # Setup auth
        monkeypatch.setattr(settings, "AUTH_ENABLED", True)
        monkeypatch.setattr(settings, "API_KEYS", ["test-key-123"])

        response = client.get(
            "/api/v1/actions",
            headers={"X-API-Key": "test-key-123"},
        )

        # Should pass auth (might fail for other reasons but not auth)
        assert response.status_code != 401


class TestActionsAPIIntegration:
    """Test Actions API with actual ActionEngine integration."""

    def test_full_action_workflow(self, client):
        """Test complete action workflow through API."""
        from app.actions.engine import get_action_engine
        from app.approvals.store import get_approval_tracker
        from unittest.mock import AsyncMock

        # Setup real engine with mocked dependencies
        engine = get_action_engine()

        # Mock the parser and validator
        engine.parser.parse = MagicMock(
            return_value=MagicMock(
                command_type="kubectl",
                action="get",
                resource_type="pod",
                namespace="default",
            )
        )

        engine.validator.validate = MagicMock(
            return_value=MagicMock(
                is_valid=True,
                allowed=True,
                requires_approval=False,
                risk_level="safe",
            )
        )

        # Test create
        create_response = client.post(
            "/api/v1/actions",
            json={
                "triage_card_id": "tc-001",
                "recommendation_id": "rec-001",
                "project": "test-project",
            },
        )

        assert create_response.status_code in [200, 201]
