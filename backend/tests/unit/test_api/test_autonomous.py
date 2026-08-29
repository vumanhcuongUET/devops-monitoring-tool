"""Unit tests for Autonomous API endpoints (Phase 4)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.actions.autonomous_executor import AutonomousExecutor
from app.feedback.analyzer import (
    ActionPattern,
    FeedbackAnalyzer,
    LearningMetrics,
)
from app.main import app


@pytest.fixture
async def autonomous_client(monkeypatch) -> AsyncClient:
    """Create async client for autonomous API testing with auth disabled."""
    from app.config import settings

    # Disable auth for testing
    monkeypatch.setattr(settings, "AUTH_ENABLED", False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client


@pytest.fixture
def mock_executor_status():
    """Create mock autonomous executor status."""
    return {
        "rate_limit_quota": {
            "delete_crashloop_pod": 3,
            "scale_deployment": 3,
            "restart_deployment": 3,
        },
        "last_executions": {
            "delete_crashloop_pod": "2026-08-21T10:00:00Z",
            "scale_deployment": None,
        },
    }


@pytest.fixture
def mock_learning_summary():
    """Create mock learning summary."""
    return {
        "analysis_window_days": 30,
        "total_actions_analyzed": 50,
        "high_confidence_patterns": ["delete", "restart"],
        "medium_confidence_patterns": ["scale"],
        "low_confidence_patterns": ["upgrade"],
        "auto_approval_candidates": ["delete"],
        "patterns_needing_review_count": 1,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@pytest.fixture
def mock_confidence_report():
    """Create mock confidence report."""
    return {
        "analysis_window_days": 30,
        "total_actions_analyzed": 50,
        "high_confidence_patterns": [
            {
                "action_type": "delete",
                "pattern": {
                    "total_actions": 20,
                    "approval_rate": 0.95,
                    "success_rate": 0.90,
                },
            }
        ],
        "medium_confidence_patterns": [
            {
                "action_type": "restart",
                "pattern": {
                    "total_actions": 15,
                    "approval_rate": 0.80,
                    "success_rate": 0.85,
                },
            }
        ],
        "low_confidence_patterns": [
            {
                "action_type": "upgrade",
                "pattern": {
                    "total_actions": 10,
                    "approval_rate": 0.50,
                    "success_rate": 0.60,
                },
            }
        ],
        "auto_approval_candidates": ["delete"],
        "patterns_needing_review": [
            {
                "action_type": "upgrade",
                "total_actions": 10,
                "approval_rate": 0.50,
                "success_rate": 0.60,
            }
        ],
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


class TestAutonomousStatusEndpoint:
    """Test GET /api/v1/autonomous/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_autonomous_status_success(self, autonomous_client: AsyncClient, mock_executor_status):
        """Test successful autonomous status retrieval."""
        with patch(
            "app.api.v1.autonomous.get_autonomous_executor"
        ) as mock_get_executor:
            mock_executor = MagicMock(spec=AutonomousExecutor)
            mock_executor.get_action_status.return_value = mock_executor_status
            mock_get_executor.return_value = mock_executor

            response = await autonomous_client.get("/api/v1/autonomous/status")

            assert response.status_code == 200
            data = response.json()
            assert "rate_limit_quota" in data
            assert "last_executions" in data

    @pytest.mark.asyncio
    async def test_get_autonomous_status_error(self, autonomous_client: AsyncClient):
        """Test autonomous status with error."""
        with patch(
            "app.api.v1.autonomous.get_autonomous_executor"
        ) as mock_get_executor:
            mock_get_executor.side_effect = Exception("Executor error")

            response = await autonomous_client.get("/api/v1/autonomous/status")

            assert response.status_code == 500


class TestLearningSummaryEndpoint:
    """Test GET /api/v1/autonomous/learning/summary endpoint."""

    @pytest.mark.asyncio
    async def test_get_learning_summary_default_window(self, autonomous_client: AsyncClient, mock_learning_summary):
        """Test learning summary with default window."""
        with patch(
            "app.api.v1.autonomous.get_feedback_analyzer"
        ) as mock_get_analyzer:
            mock_analyzer = MagicMock(spec=FeedbackAnalyzer)
            mock_analyzer.get_learning_summary.return_value = mock_learning_summary
            mock_get_analyzer.return_value = mock_analyzer

            response = await autonomous_client.get("/api/v1/autonomous/learning/summary")

            assert response.status_code == 200
            data = response.json()
            assert "total_actions_analyzed" in data
            assert "high_confidence_patterns" in data
            assert data["total_actions_analyzed"] == 50

    @pytest.mark.asyncio
    async def test_get_learning_summary_custom_window(self, autonomous_client: AsyncClient, mock_learning_summary):
        """Test learning summary with custom window."""
        with patch(
            "app.api.v1.autonomous.get_feedback_analyzer"
        ) as mock_get_analyzer:
            mock_analyzer = MagicMock(spec=FeedbackAnalyzer)
            mock_analyzer.get_learning_summary.return_value = mock_learning_summary
            mock_get_analyzer.return_value = mock_analyzer

            response = await autonomous_client.get("/api/v1/autonomous/learning/summary?window_days=60")

            assert response.status_code == 200
            # Verify analyzer was called with correct window
            mock_get_analyzer.assert_called_with(window_days=60)

    @pytest.mark.asyncio
    async def test_get_learning_summary_error(self, autonomous_client: AsyncClient):
        """Test learning summary with error."""
        with patch(
            "app.api.v1.autonomous.get_feedback_analyzer"
        ) as mock_get_analyzer:
            mock_get_analyzer.side_effect = Exception("Analyzer error")

            response = await autonomous_client.get("/api/v1/autonomous/learning/summary")

            assert response.status_code == 500


class TestConfidenceReportEndpoint:
    """Test GET /api/v1/autonomous/learning/confidence-report endpoint."""

    @pytest.mark.asyncio
    async def test_get_confidence_report_success(self, autonomous_client: AsyncClient):
        """Test successful confidence report retrieval."""
        with patch(
            "app.api.v1.autonomous.get_feedback_analyzer"
        ) as mock_get_analyzer:
            mock_analyzer = MagicMock(spec=FeedbackAnalyzer)
            mock_analyzer.generate_confidence_report.return_value = self._mock_metrics()
            mock_analyzer.get_auto_approval_candidates.return_value = ["delete"]
            mock_analyzer.get_patterns_needing_review.return_value = [
                MagicMock(
                    action_type="upgrade",
                    total_actions=10,
                    approval_rate=0.50,
                    success_rate=0.60,
                )
            ]
            mock_get_analyzer.return_value = mock_analyzer

            response = await autonomous_client.get("/api/v1/autonomous/learning/confidence-report")

            assert response.status_code == 200
            data = response.json()
            assert "high_confidence_patterns" in data
            assert "medium_confidence_patterns" in data
            assert "low_confidence_patterns" in data
            assert "auto_approval_candidates" in data
            assert "patterns_needing_review" in data

    @pytest.mark.asyncio
    async def test_get_confidence_report_custom_window(self, autonomous_client: AsyncClient):
        """Test confidence report with custom window."""
        with patch(
            "app.api.v1.autonomous.get_feedback_analyzer"
        ) as mock_get_analyzer:
            mock_analyzer = MagicMock(spec=FeedbackAnalyzer)
            mock_analyzer.generate_confidence_report.return_value = LearningMetrics()
            mock_analyzer.get_auto_approval_candidates.return_value = []
            mock_analyzer.get_patterns_needing_review.return_value = []
            mock_get_analyzer.return_value = mock_analyzer

            response = await autonomous_client.get("/api/v1/autonomous/learning/confidence-report?window_days=90")

            assert response.status_code == 200
            mock_get_analyzer.assert_called_with(window_days=90)

    @pytest.mark.asyncio
    async def test_get_confidence_report_error(self, autonomous_client: AsyncClient):
        """Test confidence report with error."""
        with patch(
            "app.api.v1.autonomous.get_feedback_analyzer"
        ) as mock_get_analyzer:
            mock_get_analyzer.side_effect = Exception("Analysis error")

            response = await autonomous_client.get("/api/v1/autonomous/learning/confidence-report")

            assert response.status_code == 500

    def _mock_metrics(self):
        """Create mock learning metrics."""
        metrics = LearningMetrics()
        metrics.total_actions_analyzed = 50
        metrics.action_patterns = {
            "delete": ActionPattern(
                action_type="delete",
                total_actions=20,
                approved_count=19,
                rejected_count=1,
                success_count=18,
                failure_count=2,
                approval_rate=0.95,
                success_rate=0.90,
                confidence_level="high",
                last_updated=datetime.now(timezone.utc),
            )
        }
        metrics.high_confidence_patterns = ["delete"]
        return metrics


class TestAutonomousAPIIntegration:
    """Test autonomous API integration scenarios."""

    @pytest.mark.asyncio
    async def test_full_autonomous_flow(self, autonomous_client: AsyncClient):
        """Test complete autonomous API flow."""
        with patch("app.api.v1.autonomous.get_autonomous_executor") as mock_exec, \
             patch("app.api.v1.autonomous.get_feedback_analyzer") as mock_analyzer:

            # Setup mocks
            executor = MagicMock(spec=AutonomousExecutor)
            executor.get_action_status.return_value = {
                "rate_limit_quota": {"delete_crashloop_pod": 3},
                "last_executions": {},
            }
            mock_exec.return_value = executor

            analyzer = MagicMock(spec=FeedbackAnalyzer)
            analyzer.get_learning_summary.return_value = {
                "total_actions_analyzed": 100,
                "high_confidence_patterns": ["delete"],
            }
            analyzer.generate_confidence_report.return_value = LearningMetrics()
            analyzer.get_auto_approval_candidates.return_value = ["delete"]
            analyzer.get_patterns_needing_review.return_value = []
            mock_analyzer.return_value = analyzer

            # Test all endpoints
            status_response = await autonomous_client.get("/api/v1/autonomous/status")
            assert status_response.status_code == 200

            summary_response = await autonomous_client.get("/api/v1/autonomous/learning/summary")
            assert summary_response.status_code == 200

            report_response = await autonomous_client.get("/api/v1/autonomous/learning/confidence-report")
            assert report_response.status_code == 200
